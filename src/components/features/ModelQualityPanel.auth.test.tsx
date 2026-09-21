import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ModelQualityPanel } from './ModelQualityPanel';

const report = {
  format_version: 1, task: 'sensor_failure', version: 'v2', status: 'rejected',
  evidence_tier: 'proxy', label_strategy: 'silence_horizon_proxy', horizon_hours: 72,
  created_at: '2026-09-21T12:00:00Z', reason_code: 'validation_rejected',
  quality_thresholds: null, split_sizes: null, baseline_validation_pr_auc: null,
  validation_metrics: null, test_metrics: null, threshold: null, champion_name: null,
};

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function response(payload: unknown, status = 200) {
  return Response.json(payload, { status });
}

it('без журнала явно входит в HttpOnly demo-сессию ОДС и повторно читает отчёт', async () => {
  const requests: Array<{ url: string; init: RequestInit | undefined }> = [];
  let authenticated = false;
  let completeSignIn: () => void = () => undefined;
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    requests.push({ url, init });
    if (url === '/api/demo-session') {
      await new Promise<void>((resolve) => { completeSignIn = resolve; });
      authenticated = true;
      return response({ active: true, profile: 'central-dispatcher', csrfToken: 'c'.repeat(40), provenance: 'simulated' }, 201);
    }
    return authenticated ? response(report) : response({}, 401);
  });
  render(<ModelQualityPanel />);
  const button = await screen.findByRole('button', { name: 'Войти в демо-режим ОДС' });
  expect(requests.map(({ url }) => url)).toEqual(['/api/model-evaluation']);
  expect(button).toHaveAttribute('type', 'button');
  expect(button).toHaveAccessibleDescription(/не является корпоративной авторизацией/i);
  button.focus();
  expect(button).toHaveFocus();
  fireEvent.click(button);
  expect(button).toBeDisabled();
  expect(screen.getByRole('status')).toHaveTextContent(/вход/i);
  completeSignIn();
  expect(await screen.findByText('72 ч')).toBeInTheDocument();
  expect(screen.getByRole('table', { name: 'Метрики качества модели' })).toBeInTheDocument();
  expect(requests.map(({ url }) => url)).toEqual(['/api/model-evaluation', '/api/demo-session', '/api/model-evaluation']);
  expect(requests[1].init).toMatchObject({ method: 'POST', credentials: 'same-origin', body: '{"profile":"central-dispatcher"}' });
  for (const { init } of requests) expect(new Headers(init?.headers).has('authorization')).toBe(false);
});

it.each(['unavailable', 'network', 'invalid'])('оставляет доступный повторный demo-вход при ошибке %s без обхода авторизации', async (failure) => {
  const requests: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    requests.push(url);
    if (url === '/api/model-evaluation') return response({}, 401);
    if (failure === 'network') throw new Error('Служебные подробности не для UI');
    return response({}, failure === 'unavailable' ? 503 : 201);
  });
  render(<ModelQualityPanel />);
  fireEvent.click(await screen.findByRole('button', { name: 'Войти в демо-режим ОДС' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/не удалось войти/i);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Войти в демо-режим ОДС' })).toBeEnabled());
  expect(requests).toEqual(['/api/model-evaluation', '/api/demo-session']);
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
  expect(screen.queryByText(/служебные подробности/i)).not.toBeInTheDocument();
});

it('не предлагает вход и не создаёт сессию, когда отчёт недоступен с 503', async () => {
  vi.stubGlobal('fetch', async () => response({}, 503));
  render(<ModelQualityPanel />);
  expect(await screen.findByRole('heading', { name: 'Отчёт об оценке недоступен' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /войти/i })).not.toBeInTheDocument();
});

it('после успешного demo-входа сохраняет 503 как недоступность отчёта', async () => {
  let authenticated = false;
  vi.stubGlobal('fetch', async (url: string) => {
    if (url === '/api/demo-session') {
      authenticated = true;
      return response({ active: true, profile: 'central-dispatcher', csrfToken: 'c'.repeat(40), provenance: 'simulated' }, 201);
    }
    return response({}, authenticated ? 503 : 401);
  });
  render(<ModelQualityPanel />);
  fireEvent.click(await screen.findByRole('button', { name: 'Войти в демо-режим ОДС' }));
  expect(await screen.findByRole('heading', { name: 'Отчёт об оценке недоступен' })).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});
