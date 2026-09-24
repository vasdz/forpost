// @vitest-environment node
import { execFile, fork } from 'node:child_process';
import { once } from 'node:events';
import net from 'node:net';
import path from 'node:path';
import { promisify } from 'node:util';
import { setTimeout as delay } from 'node:timers/promises';
import { expect, it } from 'vitest';

const execute = promisify(execFile);

function isAlive(pid) {
  try { process.kill(pid, 0); return true; } catch (error) {
    if (error.code === 'ESRCH') return false;
    throw error;
  }
}

async function isListening(port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host: '127.0.0.1', port });
    socket.setTimeout(300);
    socket.once('connect', () => { socket.destroy(); resolve(true); });
    socket.once('error', () => { socket.destroy(); resolve(false); });
    socket.once('timeout', () => { socket.destroy(); resolve(false); });
  });
}

async function until(predicate, milliseconds = 15000) {
  const deadline = Date.now() + milliseconds;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await delay(100);
  }
  throw new Error('Истёк срок ожидания локального дерева процессов');
}

it.skipIf(process.platform !== 'win32')('закрывает реальный Next worker и API при остановке Windows launcher', async () => {
  expect(await isListening(3000), 'Тест не должен затрагивать чужой Next').toBe(false);
  expect(await isListening(8000), 'Тест не должен затрагивать чужой API').toBe(false);
  const launcher = fork(new URL('./fixtures/local-stack-lifecycle.mjs', import.meta.url), [], {
    env: {
      ...process.env,
      // Тест поднимает настоящий API, поэтому не зависит от активированного shell-окружения.
      PATH: `${path.resolve('.venv/Scripts')}${path.delimiter}${process.env.PATH ?? ''}`,
    },
    stdio: ['ignore', 'pipe', 'pipe', 'ipc'], windowsHide: true,
  });
  const owned = new Set([launcher.pid]);
  const exited = once(launcher, 'exit');
  // Потоки дренируются, но окружение и возможные служебные секреты не печатаются.
  launcher.stdout.resume();
  launcher.stderr.resume();
  try {
    const [pids] = await Promise.race([
      once(launcher, 'message'),
      delay(5000).then(() => { throw new Error('Launcher не вернул PID'); }),
    ]);
    owned.add(pids.api);
    owned.add(pids.next);
    await until(async () => await isListening(3000) && await isListening(8000), 30000);
    expect(Number.isSafeInteger(pids.next)).toBe(true);
    const { stdout } = await execute('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
      '& { param([int]$ownedParent) Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $ownedParent } | Select-Object -ExpandProperty ProcessId }',
      String(pids.next),
    ], { windowsHide: true, timeout: 5000 });
    const descendants = stdout.trim().split(/\s+/).map(Number).filter((pid) => pid > 0);
    expect(descendants.length, 'Next обязан создать worker и независимого тестового потомка').toBeGreaterThanOrEqual(2);
    descendants.forEach((pid) => owned.add(pid));
    expect([...owned].every((pid) => isAlive(pid)), 'Все отслеживаемые процессы живы до остановки').toBe(true);
    launcher.send('stop');
    await until(() => [...owned].every((pid) => !isAlive(pid)), 10000);
    expect(await exited).toEqual([143, null]);
    expect(await isListening(3000)).toBe(false);
    expect(await isListening(8000)).toBe(false);
  } finally {
    await Promise.all([...owned].map(async (pid) => {
      if (Number.isSafeInteger(pid) && isAlive(pid)) {
        await execute('taskkill', ['/PID', String(pid), '/T', '/F'], {
          windowsHide: true, timeout: 5000,
        }).catch(() => undefined);
      }
    }));
  }
}, 60000);
