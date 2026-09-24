import type { ModelMetrics, QualityThresholds } from '@/data/modelEvaluationClient';
import { Chart } from './Chart';
import { buildModelQualityComparisonOption } from './chartOptions';

export function ModelQualityComparisonChart({
  validation,
  test,
  thresholds,
}: {
  validation: ModelMetrics;
  test: ModelMetrics;
  thresholds: QualityThresholds;
}) {
  const rows = [
    ['Точность', validation.precision, test.precision, thresholds.minimumPrecision],
    ['Полнота', validation.recall, test.recall, thresholds.minimumRecall],
  ].map(([metric, validationValue, testValue, minimum]) => [
    metric,
    formatPercent(Number(validationValue)),
    formatPercent(Number(testValue)),
    formatPercent(Number(minimum)),
  ]);

  return <Chart
    label="Сравнение качества модели"
    description="Точность и полнота на временной валидации сопоставлены с финальным отложенным тестом и обязательными минимальными порогами."
    option={buildModelQualityComparisonOption({
      validation,
      test,
      minimums: { precision: thresholds.minimumPrecision, recall: thresholds.minimumRecall },
    })}
    columns={['Метрика', 'Валидация', 'Финальный тест', 'Минимум']}
    rows={rows}
  />;
}

function formatPercent(value: number): string {
  return value.toLocaleString('ru-RU', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
}
