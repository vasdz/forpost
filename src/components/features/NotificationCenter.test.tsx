import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { NotificationCenter } from './NotificationCenter';

const predictionApi = vi.hoisted(() => ({ fetchPredictionFeed: vi.fn() }));
const operations = vi.hoisted(() => ({
  getDemoSession: vi.fn(), startDemoSession: vi.fn(), recordPredictionDecision: vi.fn(), createPredictionServiceDraft: vi.fn(),
}));
vi.mock('@/data/predictionsClient', () => predictionApi);
vi.mock('@/data/operationsClient', () => operations);
vi.mock('@/data/LocalSituationProvider', () => ({
  useLocalSituation: () => ({
    status: 'ready',
    snapshot: {
      events: [{
        canonicalId: 'a'.repeat(64), eventId: 'event-1', channelId: 'channel-1',
        recordedAt: '2026-09-24T08:30:00', isAlarm: true, sensorValue: 'ПОЖАР',
        qualityCode: 'valid', analysisEligible: true, provenance: 'observed',
      }],
    },
  }),
}));

const prediction = {
  id: 'prediction-1', entityType: 'sensor', entityId: 'channel-1',
  predictionType: 'sensor_failure', probability: 0.82, anomalyScore: null,
  evidenceTier: 'proxy', calibrated: true, provenance: 'derived', confidence: null,
  modelMetrics: { precision: 0.8, recall: 0.7, f1: 0.75, prAuc: 0.81, brierScore: 0.13 },
  qualityStatus: 'passed', limitations: ['Прокси прекращения телеметрии'],
  predictedAt: '2099-09-24T09:00:00Z', horizonHours: 24, modelVersion: 'v7',
  factors: [{ factor: 'silence', weight: 1, description: 'Длительность тишины' }],
  recommendedAction: 'Проверить канал и питание датчика', priority: 'high', status: 'new',
} as const;

afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('проводит диспетчера от уведомления до решения и связанного черновика', async () => {
  predictionApi.fetchPredictionFeed.mockResolvedValue({
    status: 'ready', availableTypes: ['sensor_failure'], predictions: [prediction],
  });
  operations.getDemoSession.mockResolvedValue(null);
  operations.startDemoSession.mockResolvedValue({ active: true, profile: 'central-dispatcher', csrfToken: 'c'.repeat(40), provenance: 'simulated' });
  operations.recordPredictionDecision.mockResolvedValue({ status: 'recorded', predictionId: 'prediction-1', auditRecordId: 7 });
  operations.createPredictionServiceDraft.mockResolvedValue({ draftId: 'draft-1' });

  render(<NotificationCenter />);
  fireEvent.click(await screen.findByRole('button', { name: /канал channel-1/i }));
  const dialog = screen.getByRole('dialog', { name: /прогноз для channel-1/i });
  expect(within(dialog).getByText('Проверить канал и питание датчика')).toBeInTheDocument();
  expect(within(dialog).getByText('ПОЖАР')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Войти как диспетчер ОДС' }));
  await waitFor(() => expect(operations.startDemoSession).toHaveBeenCalled());
  fireEvent.change(screen.getByRole('combobox', { name: 'Решение диспетчера' }), { target: { value: 'confirmed' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Обоснование решения' }), { target: { value: 'Назначена проверка объекта дежурной бригадой' } });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить решение' }));
  expect(await screen.findByText(/решение сохранено/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Создать черновик заявки' }));
  expect(await screen.findByText(/черновик создан/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Открыть заявки' })).toHaveAttribute('href', '/applications');
  expect(operations.createPredictionServiceDraft).toHaveBeenCalledWith(
    'prediction-1', 'c'.repeat(40),
  );
});
it('различает недоступную модель и отсутствие активных уведомлений', async () => {
  operations.getDemoSession.mockResolvedValue(null);
  predictionApi.fetchPredictionFeed.mockResolvedValueOnce({ status: 'unavailable', availableTypes: [], predictions: [] });
  const first = render(<NotificationCenter />);
  expect(await screen.findByRole('heading', { name: 'Уведомления недоступны' })).toBeInTheDocument();
  first.unmount();
  predictionApi.fetchPredictionFeed.mockResolvedValueOnce({ status: 'ready', availableTypes: ['sensor_failure'], predictions: [] });
  render(<NotificationCenter />);
  expect(await screen.findByRole('heading', { name: 'Активных уведомлений нет' })).toBeInTheDocument();
});
