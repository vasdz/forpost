import { spawn } from 'node:child_process';

// Только тестовый Next CLI получает дополнительного реального потомка без IPC.
// Он не завершится автоматически по disconnect, поэтому выявляет orphan-процессы.
if (/[\\/]next[\\/]dist[\\/]bin[\\/]next$/.test(process.argv[1] ?? '') && process.argv.includes('dev')) {
  spawn(process.execPath, ['--eval', 'setInterval(() => {}, 1000)'], {
    stdio: 'ignore', windowsHide: true, shell: false, detached: true,
    env: { ...process.env, NODE_OPTIONS: '' },
  });
}
