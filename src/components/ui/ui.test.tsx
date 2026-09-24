import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Modal } from './Modal';
import { MultiSelect } from './MultiSelect';
import { Table } from './Table';
import { Tabs } from './Tabs';
import { Badge } from './Badge';
import { Button } from './Button';
import { Card } from './Card';

afterEach(cleanup);

describe('Tabs', () => {
  it('переключает активную вкладку стрелкой вправо', () => {
    render(<Tabs tabs={[{ id: 'one', label: 'Один', content: 'Первый' }, { id: 'two', label: 'Два', content: 'Второй' }]} />);
    const firstTab = screen.getByRole('tab', { name: 'Один' });
    firstTab.focus();
    fireEvent.keyDown(firstTab, { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'Два' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Второй');
  });

  it('безопасно обрабатывает пустой список вкладок', () => {
    const { container } = render(<Tabs tabs={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('Badge и Button', () => {
  it('используют безопасные варианты по умолчанию при некорректных runtime-значениях', () => {
    render(
      <>
        <Badge tone={'unknown' as never}>Статус</Badge>
        <Button variant={'unknown' as never} size={'unknown' as never}>Продолжить</Button>
      </>,
    );

    expect(screen.getByText('Статус')).toHaveClass('border-[var(--color-border)]');
    expect(screen.getByRole('button', { name: 'Продолжить' })).toHaveClass(
      'border-[var(--color-data)]',
      'h-10',
    );
  });

  it('формируют плоскую рабочую поверхность с семантическим статусом', () => {
    render(
      <Card aria-label="Контекст наблюдения">
        <Badge tone="critical">Критично</Badge>
        <Button>Открыть</Button>
      </Card>,
    );

    expect(screen.getByLabelText('Контекст наблюдения')).toHaveClass('surface');
    expect(screen.getByText('Критично')).toHaveClass('status-critical');
    expect(screen.getByRole('button', { name: 'Открыть' })).toHaveClass('control-surface');
  });
});

describe('Modal', () => {
  it('закрывается по Escape и возвращает управление обработчику', () => {
    const onClose = vi.fn();
    render(<Modal isOpen onClose={onClose} title="Паспорт объекта"><button type="button">Действие</button></Modal>);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe('Table', () => {
  it('объявляет загрузку, ошибку и пустую выборку', () => {
    const columns = [{ key: 'id' as const, label: 'ID' }];
    const { rerender } = render(<Table ariaLabel="Реестр" columns={columns} rows={[]} loading />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    rerender(<Table ariaLabel="Реестр" columns={columns} rows={[]} error="Источник недоступен" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Источник недоступен');
    rerender(<Table ariaLabel="Реестр" columns={columns} rows={[]} />);
    expect(screen.getByText('Записи по заданным фильтрам не найдены.')).toBeInTheDocument();
  });
  it('сортирует строки при нажатии на заголовок', () => {
    render(
      <Table
        ariaLabel="Датчики"
        columns={[{ key: 'name', label: 'Название', sortable: true }]}
        rows={[{ id: '1', name: 'Датчик Б' }, { id: '2', name: 'Датчик А' }]}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Название/ }));
    expect(screen.getAllByRole('row')[1]).toHaveTextContent('Датчик А');
  });

  it('открывает строку по явному действию пользователя', () => {
    const onRowClick = vi.fn();
    render(<Table ariaLabel="Датчики" columns={[{ key: 'name', label: 'Название' }]} rows={[{ id: '1', name: 'Датчик А' }]} onRowClick={onRowClick} />);
    fireEvent.click(screen.getByText('Датчик А'));
    expect(onRowClick).toHaveBeenCalledWith({ id: '1', name: 'Датчик А' });
  });
});

describe('MultiSelect', () => {
  it('передаёт выбранные значения', () => {
    const onChange = vi.fn();
    render(<MultiSelect label="Районы" options={[{ value: 'one', label: 'Первый' }, { value: 'two', label: 'Второй' }]} value={[]} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /Районы/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Первый' }));
    expect(onChange).toHaveBeenCalledWith(['one']);
  });
});
