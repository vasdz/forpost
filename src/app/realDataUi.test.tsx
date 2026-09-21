import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ApplicationsPage from './applications/page';
import DesignSystemPage from './design-system/page';
import FireRiskPage from './fire-risk/page';
import InfrastructureWearPage from './infrastructure-wear/page';
import JournalsPage from './journals/page';
import OverviewPage from './page';
import RegistriesPage from './registries/page';
import SensorFailurePage from './sensor-failure/page';
import UnauthorizedAccessPage from './unauthorized-access/page';
import TopologyPage from './topology/page';

const operations = vi.hoisted(() => ({
  fetchIncidentDecisions: vi.fn().mockResolvedValue([]),
  fetchServiceDrafts: vi.fn().mockResolvedValue([{
    draftId: 'draft-1',
    incidentId: 'a'.repeat(64),
    targetId: 'channel-1',
    category: 'sensor_check',
    priority: 'high',
    recommendedAction: 'Проверить канал связи',
    dueAt: '2026-09-19T12:00:00Z',
    authorId: 'dispatcher-1',
    createdAt: '2026-09-18T12:00:00Z',
    provenance: 'simulated',
  }]),
  fetchTopology: vi.fn().mockResolvedValue({
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      id: 'object-1',
      geometry: { type: 'MultiLineString', coordinates: [[[0, 0], [0.4, 0]]] },
      properties: {
        objectId: 'object-1', parentId: null, objectKind: 'controlHouse',
        dispatcherName: 'Объект 1', geometrySource: 'synthetic',
        provenance: 'derived', coordinateProvenance: 'simulated',
      },
    }],
    metadata: { title: 'Схема объектов', geometrySource: 'synthetic', coordinateProvenance: 'simulated' },
  }),
  getDemoSession: vi.fn().mockResolvedValue(null),
  startDemoSession: vi.fn(),
  recordIncidentDecision: vi.fn(),
  createServiceDraft: vi.fn(),
}));

const predictionState = vi.hoisted(() => {
  const predictions = [
    {
      id: 'prediction-sensor', entityType: 'sensor', entityId: 'channel-1',
      predictionType: 'sensor_failure', probability: 0.82, anomalyScore: null,
      evidenceTier: 'proxy', calibrated: true, provenance: 'derived',
      confidence: { lower: 0.74, upper: 0.88 },
      modelMetrics: { precision: 0.78, recall: 0.68, f1: 0.72, prAuc: 0.76, brierScore: 0.14 },
      qualityStatus: 'passed', limitations: ['Прокси-метка тишины не подтверждает физический отказ'],
      predictedAt: '2026-09-18T12:00:00Z', horizonHours: 24, modelVersion: 'v1',
      factors: [{ factor: 'Давность сигнала', weight: 0.7, description: 'Канал дольше обычного не передавал события' }],
      recommendedAction: 'Проверить канал и питание датчика', priority: 'high', status: 'new',
    },
    {
      id: 'prediction-fire', entityType: 'location', entityId: 'object-1',
      predictionType: 'fire_risk', probability: null, anomalyScore: 0.91,
      evidenceTier: 'anomaly', calibrated: false, provenance: 'derived', confidence: null,
      modelMetrics: null, qualityStatus: 'limited',
      limitations: ['Нет подтверждённой разметки пожарных инцидентов'],
      predictedAt: '2026-09-18T12:00:00Z', horizonHours: 24, modelVersion: 'v1',
      factors: [{ factor: 'Комбинация сигналов', weight: 1, description: 'Нетипичная совместная активность каналов' }],
      recommendedAction: 'Проверить первичные сигналы', priority: 'high', status: 'new',
    },
    {
      id: 'prediction-wear', entityType: 'location', entityId: 'object-1',
      predictionType: 'infrastructure_wear', probability: null, anomalyScore: 0.64,
      evidenceTier: 'scenario', calibrated: false, provenance: 'simulated', confidence: null,
      modelMetrics: null, qualityStatus: 'limited', limitations: ['История ремонтов недоступна'],
      predictedAt: '2026-09-18T12:00:00Z', horizonHours: 168, modelVersion: 'v1',
      factors: [{ factor: 'Возрастной сценарий', weight: 1, description: 'Оценка построена на сценарных параметрах' }],
      recommendedAction: 'Уточнить паспорт оборудования', priority: 'medium', status: 'new',
    },
  ];
  return {
    fetchPredictions: vi.fn().mockResolvedValue(predictions),
    fetchPredictionFeed: vi.fn().mockResolvedValue({
      status: 'ready', availableTypes: ['sensor_failure'], predictions,
    }),
  };
});

vi.mock('@/data/operationsClient', async () => {
  const actual = await vi.importActual<typeof import('@/data/operationsClient')>('@/data/operationsClient');
  return { ...actual, ...operations };
});
vi.mock('@/data/predictionsClient', () => predictionState);

const localSituationState = vi.hoisted(() => ({
  value: {
    status: 'ready' as const,
    snapshot: {
      sourceAvailability: {
        events: true,
        channels: true,
        objects: true,
        access_events: false,
        maintenance_history: false,
        ml_predictions: false,
        work_permits: false,
      },
      channels: [{
        channelId: 'channel-1',
        engineeringSystemType: 'СМВУ',
        sensorType: 'Контактный',
        engineeringSystemTag: 'tag-1',
        sensorName: 'Датчик 1',
        objectId: 'object-1',
      }],
      objects: [{
        objectId: 'object-1',
        hierarchyLevel: '1',
        parentId: null,
        objectKind: 'Коллектор',
        dispatcherName: 'Объект 1',
      }],
      events: [{
        canonicalId: 'a'.repeat(64),
        eventId: 'event-1',
        channelId: 'channel-1',
        recordedAt: '2026-08-01T23:59:58',
        isAlarm: true,
        sensorValue: 'наблюдаемое значение',
        qualityCode: 'valid',
        analysisEligible: true,
        provenance: 'observed',
      }],
    },
  },
}));

vi.mock('@/data/LocalSituationProvider', () => ({
  useLocalSituation: () => localSituationState.value,
}));
vi.mock('echarts-for-react', () => ({ default: () => null }));

afterEach(cleanup);

describe('интерфейс локального снимка', () => {
  it('показывает на обзоре только наблюдаемые события без прогнозов и рисков', () => {
    render(<OverviewPage />);

    expect(screen.getByRole('heading', { name: 'Наблюдаемая оперативная обстановка' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Журнал наблюдаемых событий' });
    expect(within(table).getByText('event-1')).toBeInTheDocument();
    expect(within(table).getByText('Отметка о сработке')).toBeInTheDocument();
    expect(screen.queryByText(/Топ-10 рисков/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Активные прогнозы/i)).not.toBeInTheDocument();
  });

  it('показывает proxy-прогноз отдельно от наблюдаемых каналов и событий', async () => {
    render(<SensorFailurePage />);

    expect(screen.getByRole('heading', { name: 'Наблюдения по каналам датчиков' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Наблюдения датчиков' })).toHaveTextContent('event-1');
    expect(await screen.findByText('82%')).toBeInTheDocument();
    expect(screen.getByText('Прокси-модель')).toBeInTheDocument();
    expect(screen.getByText(/не подтверждает физический отказ/i)).toBeInTheDocument();
  });

  it('даёт поиск, экспорт и детали только для доступных реестров', () => {
    render(<RegistriesPage />);

    expect(screen.getByRole('heading', { name: 'Реестры наблюдаемого снимка' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Оборудование' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Датчики' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Журналы ОДС' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'АРМ-Контроль' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: 'Поиск по реестру оборудования' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Экспортировать оборудование в CSV' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Объекты' })).toHaveTextContent('object-1');
  });

  it('показывает современный журнал технологических событий из локального снимка', () => {
    render(<JournalsPage />);

    expect(screen.getByRole('heading', { name: 'Журнал технологических событий' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: 'Поиск по журналу событий' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Экспортировать журнал в CSV' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Журнал технологических событий' })).toHaveTextContent('event-1');
  });

  it('открывает проверяемую карточку тревоги с происхождением и действием', async () => {
    render(<JournalsPage />);

    fireEvent.click(screen.getByRole('button', { name: `Открыть запись ${'a'.repeat(64)}` }));

    const dialog = await screen.findByRole('dialog', { name: 'Карточка инцидента' });
    expect(within(dialog).getByText('Наблюдение источника')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Войти как диспетчер ОДС' })).toBeInTheDocument();
  });

  it('показывает только локальные simulated-черновики заявок', async () => {
    render(<ApplicationsPage />);

    expect(screen.getByRole('heading', { name: 'Черновики заявок' })).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: 'Локальные черновики заявок' });
    expect(table).toHaveTextContent('Проверить канал связи');
    expect(table).toHaveTextContent('Симуляция');
  });

  it('даёт схеме постоянное предупреждение и табличную альтернативу', async () => {
    render(<TopologyPage />);

    expect(screen.getByRole('heading', { name: 'Схема объектов' })).toBeInTheDocument();
    expect(screen.getByText(/координаты условные/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('table', { name: 'Табличное представление схемы объектов' })).toHaveTextContent('Объект 1'));
  });

  it('не показывает anomaly score как результат без валидированной модели', async () => {
    render(<FireRiskPage />);

    expect(await screen.findByRole('heading', { name: 'Прогнозы недоступны' })).toBeInTheDocument();
    expect(screen.queryByText(/Индекс аномалии/)).not.toBeInTheDocument();
    expect(screen.queryByText('91%')).not.toBeInTheDocument();
  });

  it('не показывает сценарный износ как подтверждённый результат', async () => {
    render(<InfrastructureWearPage />);

    expect(await screen.findByRole('heading', { name: 'Прогнозы недоступны' })).toBeInTheDocument();
    expect(screen.queryByText('Сценарий')).not.toBeInTheDocument();
    expect(screen.getByText(/сценарный экспорт.*не найден/i)).toBeInTheDocument();
  });

  it.each([
    ['Несанкционированный доступ', UnauthorizedAccessPage],
    ['Настройки недоступны', DesignSystemPage],
  ])('не формирует результаты без источника: %s', async (heading, Page) => {
    render(<Page />);

    expect(await screen.findByRole('heading', { name: heading, level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/не подключен|отсутствуют|не формируется|не найден/i)).toBeInTheDocument();
  });
});
