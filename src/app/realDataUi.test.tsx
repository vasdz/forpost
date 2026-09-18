import { cleanup, render, screen, within } from '@testing-library/react';
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
      }],
      objects: [{
        objectId: 'object-1',
        hierarchyLevel: '1',
        parentId: null,
        objectKind: 'Коллектор',
        dispatcherName: 'Объект 1',
      }],
      events: [{
        eventId: 'event-1',
        channelId: 'channel-1',
        recordedAt: '2026-08-01T23:59:58',
        isAlarm: true,
        sensorValue: 'наблюдаемое значение',
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

  it('оставляет в реестрах только доступные каналы и объекты', () => {
    render(<RegistriesPage />);

    expect(screen.getByRole('heading', { name: 'Реестры наблюдаемого снимка' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Каналы СМВУ' })).toHaveTextContent('channel-1');
    expect(screen.getByRole('table', { name: 'Объекты' })).toHaveTextContent('object-1');
    expect(screen.queryByRole('tab', { name: /АРМ-Контроль/i })).not.toBeInTheDocument();
  });

  it.each([
    ['Пожарный риск недоступен', FireRiskPage],
    ['Несанкционированный доступ недоступен', UnauthorizedAccessPage],
    ['Износ инфраструктуры недоступен', InfrastructureWearPage],
    ['Журнал решений недоступен', JournalsPage],
    ['Заявки недоступны', ApplicationsPage],
    ['Настройки недоступны', DesignSystemPage],
  ])('не формирует вымышленные результаты: %s', (heading, Page) => {
    render(<Page />);

    expect(screen.getByRole('heading', { name: heading, level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/не подключен|отсутствуют|не формируется/i)).toBeInTheDocument();
  });
});
