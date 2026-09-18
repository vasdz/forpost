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

vi.mock('@/data/operationsClient', async () => {
  const actual = await vi.importActual<typeof import('@/data/operationsClient')>('@/data/operationsClient');
  return { ...actual, ...operations };
});

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

  it('показывает на странице датчиков только наблюдаемые каналы и события', () => {
    render(<SensorFailurePage />);

    expect(screen.getByRole('heading', { name: 'Наблюдения по каналам датчиков' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Наблюдения датчиков' })).toHaveTextContent('event-1');
    expect(screen.queryByRole('columnheader', { name: 'Вероятность' })).not.toBeInTheDocument();
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

  it.each([
    ['Пожарный риск недоступен', FireRiskPage],
    ['Несанкционированный доступ недоступен', UnauthorizedAccessPage],
    ['Износ инфраструктуры недоступен', InfrastructureWearPage],
    ['Настройки недоступны', DesignSystemPage],
  ])('не формирует вымышленные результаты: %s', (heading, Page) => {
    render(<Page />);

    expect(screen.getByRole('heading', { name: heading, level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/не подключен|отсутствуют|не формируется/i)).toBeInTheDocument();
  });
});
