export type EvaluationStatus = 'rejected' | 'published';
export type EvaluationReasonCode =
  | 'configuration_invalid'
  | 'source_unavailable'
  | 'dataset_unavailable'
  | 'training_unavailable'
  | 'validation_rejected'
  | 'test_rejected'
  | 'inference_unavailable'
  | 'release_unavailable';
export type CandidateName =
  | 'extra_trees_isotonic'
  | 'extra_trees_sigmoid'
  | 'hist_gradient_boosting_isotonic'
  | 'hist_gradient_boosting_sigmoid'
  | 'logistic_regression_isotonic'
  | 'logistic_regression_sigmoid';

export type ModelMetrics = {
  precision: number;
  recall: number;
  f1: number;
  prAuc: number;
  rocAuc: number;
  brierScore: number;
  expectedCalibrationError: number;
  alertRate: number;
};

export type QualityThresholds = {
  minimumPrecision: number;
  minimumRecall: number;
  maximumAlertRate: number;
  maximumExpectedCalibrationError: number;
  maximumBrierScore: number;
  minimumBaselinePrAucDelta: number;
};

export type SplitSizes = { fit: number; calibration: number; validation: number; test: number };

export type ModelEvaluation = {
  formatVersion: 1;
  task: 'sensor_failure';
  version: string;
  status: EvaluationStatus;
  evidenceTier: 'proxy';
  labelStrategy: 'silence_horizon_proxy';
  createdAt: string;
  reasonCode: EvaluationReasonCode | null;
  qualityThresholds: QualityThresholds | null;
  splitSizes: SplitSizes | null;
  baselineValidationPrAuc: number | null;
  validationMetrics: ModelMetrics | null;
  testMetrics: ModelMetrics | null;
  threshold: number | null;
  championName: CandidateName | null;
};

export type ModelEvaluationFeed =
  | { status: 'ready'; evaluation: ModelEvaluation }
  | { status: 'unavailable' };

const metricKeys = ['precision', 'recall', 'f1', 'pr_auc', 'roc_auc', 'brier_score', 'expected_calibration_error', 'alert_rate'] as const;
const thresholdKeys = ['minimum_precision', 'minimum_recall', 'maximum_alert_rate', 'maximum_expected_calibration_error', 'maximum_brier_score', 'minimum_baseline_pr_auc_delta'] as const;
const splitKeys = ['fit', 'calibration', 'validation', 'test'] as const;
const reportKeys = ['format_version', 'task', 'version', 'status', 'evidence_tier', 'label_strategy', 'created_at', 'reason_code', 'quality_thresholds', 'split_sizes', 'baseline_validation_pr_auc', 'validation_metrics', 'test_metrics', 'threshold', 'champion_name'] as const;
const reasonCodes: readonly EvaluationReasonCode[] = ['configuration_invalid', 'source_unavailable', 'dataset_unavailable', 'training_unavailable', 'validation_rejected', 'test_rejected', 'inference_unavailable', 'release_unavailable'];
const candidates: readonly CandidateName[] = ['extra_trees_isotonic', 'extra_trees_sigmoid', 'hist_gradient_boosting_isotonic', 'hist_gradient_boosting_sigmoid', 'logistic_regression_isotonic', 'logistic_regression_sigmoid'];

export async function fetchModelEvaluation(
  fetcher: typeof globalThis.fetch = globalThis.fetch,
): Promise<ModelEvaluationFeed> {
  try {
    const response = await fetcher('/api/model-evaluation', { cache: 'no-store' });
    if (!response.ok || !response.headers.get('content-type')?.toLowerCase().includes('application/json')) return unavailableFeed();
    const evaluation = parseModelEvaluation(await response.json());
    return evaluation === null ? unavailableFeed() : { status: 'ready', evaluation };
  } catch {
    return unavailableFeed();
  }
}

function unavailableFeed(): ModelEvaluationFeed {
  return { status: 'unavailable' };
}

function parseModelEvaluation(value: unknown): ModelEvaluation | null {
  if (!isExactRecord(value, reportKeys)
    || value.format_version !== 1
    || value.task !== 'sensor_failure'
    || !isVersion(value.version)
    || !isEvaluationStatus(value.status)
    || value.evidence_tier !== 'proxy'
    || value.label_strategy !== 'silence_horizon_proxy'
    || !isTimestampWithTimezone(value.created_at)
    || !isReasonCodeOrNull(value.reason_code)
    || !isQualityThresholdsOrNull(value.quality_thresholds)
    || !isSplitSizesOrNull(value.split_sizes)
    || !isUnitNumberOrNull(value.baseline_validation_pr_auc)
    || !isMetricsOrNull(value.validation_metrics)
    || !isMetricsOrNull(value.test_metrics)
    || !isThresholdOrNull(value.threshold)
    || !isCandidateOrNull(value.champion_name)) return null;

  if (value.status === 'published' && (!allEvidencePresent(value) || value.reason_code !== null)) return null;
  if (value.status === 'rejected' && (value.reason_code === null || value.test_metrics !== null)) return null;

  return {
    formatVersion: 1,
    task: 'sensor_failure',
    version: value.version,
    status: value.status,
    evidenceTier: 'proxy',
    labelStrategy: 'silence_horizon_proxy',
    createdAt: value.created_at,
    reasonCode: value.reason_code,
    qualityThresholds: mapThresholds(value.quality_thresholds),
    splitSizes: value.split_sizes,
    baselineValidationPrAuc: value.baseline_validation_pr_auc,
    validationMetrics: mapMetrics(value.validation_metrics),
    testMetrics: mapMetrics(value.test_metrics),
    threshold: value.threshold,
    championName: value.champion_name,
  };
}

function allEvidencePresent(value: Record<string, unknown>): boolean {
  return value.quality_thresholds !== null
    && value.split_sizes !== null
    && value.baseline_validation_pr_auc !== null
    && value.validation_metrics !== null
    && value.test_metrics !== null
    && value.threshold !== null
    && value.champion_name !== null;
}

function mapMetrics(value: Record<string, number> | null): ModelMetrics | null {
  if (value === null) return null;
  return {
    precision: value.precision, recall: value.recall, f1: value.f1, prAuc: value.pr_auc,
    rocAuc: value.roc_auc, brierScore: value.brier_score,
    expectedCalibrationError: value.expected_calibration_error, alertRate: value.alert_rate,
  };
}

function mapThresholds(value: Record<string, number> | null): QualityThresholds | null {
  if (value === null) return null;
  return {
    minimumPrecision: value.minimum_precision, minimumRecall: value.minimum_recall,
    maximumAlertRate: value.maximum_alert_rate,
    maximumExpectedCalibrationError: value.maximum_expected_calibration_error,
    maximumBrierScore: value.maximum_brier_score,
    minimumBaselinePrAucDelta: value.minimum_baseline_pr_auc_delta,
  };
}

function isExactRecord(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

function isUnitNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isUnitNumberOrNull(value: unknown): value is number | null {
  return value === null || isUnitNumber(value);
}

function isMetricsOrNull(value: unknown): value is Record<string, number> | null {
  return value === null || (isExactRecord(value, metricKeys)
    && isUnitNumber(value.precision) && isUnitNumber(value.recall)
    && isUnitNumber(value.f1) && isUnitNumber(value.pr_auc)
    && isUnitNumber(value.roc_auc) && isUnitNumber(value.brier_score)
    && isUnitNumber(value.expected_calibration_error) && isUnitNumber(value.alert_rate));
}

function isQualityThresholdsOrNull(value: unknown): value is Record<string, number> | null {
  return value === null || (isExactRecord(value, thresholdKeys)
    && isUnitNumber(value.minimum_precision) && isUnitNumber(value.minimum_recall)
    && isUnitNumber(value.maximum_alert_rate) && isUnitNumber(value.maximum_expected_calibration_error)
    && isUnitNumber(value.maximum_brier_score) && isUnitNumber(value.minimum_baseline_pr_auc_delta));
}

function isSplitSizesOrNull(value: unknown): value is SplitSizes | null {
  return value === null || (isExactRecord(value, splitKeys)
    && isPositiveSafeInteger(value.fit) && isPositiveSafeInteger(value.calibration)
    && isPositiveSafeInteger(value.validation) && isPositiveSafeInteger(value.test));
}

function isPositiveSafeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}

function isThresholdOrNull(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value) && value > 0 && value < 1);
}

function isVersion(value: unknown): value is string {
  return typeof value === 'string' && /^v[1-9]\d*$/.test(value) && value.length <= 32;
}

function isEvaluationStatus(value: unknown): value is EvaluationStatus {
  return value === 'rejected' || value === 'published';
}

function isReasonCodeOrNull(value: unknown): value is EvaluationReasonCode | null {
  return value === null || (typeof value === 'string' && reasonCodes.includes(value as EvaluationReasonCode));
}

function isCandidateOrNull(value: unknown): value is CandidateName | null {
  return value === null || (typeof value === 'string' && candidates.includes(value as CandidateName));
}

function isTimestampWithTimezone(value: unknown): value is string {
  if (typeof value !== 'string' || value.length < 20 || value.length > 35 || value[10] !== 'T') return false;
  const timezoneStart = value.endsWith('Z') ? value.length - 1 : value.length - 6;
  if (timezoneStart < 19 || (value.endsWith('Z') ? false : !isTimezoneOffset(value, timezoneStart))) return false;
  const fractionalLength = timezoneStart - 19;
  if (fractionalLength !== 0 && (fractionalLength < 2 || fractionalLength > 10 || value[19] !== '.')) return false;
  const digitPositions = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18];
  return value[4] === '-' && value[7] === '-' && value[13] === ':' && value[16] === ':'
    && digitPositions.every((position) => isDigit(value.charAt(position)))
    && [...value.slice(20, timezoneStart)].every(isDigit)
    && Number.isFinite(Date.parse(value));
}

function isTimezoneOffset(value: string, start: number): boolean {
  return (value.charAt(start) === '+' || value.charAt(start) === '-') && value.charAt(start + 3) === ':'
    && isDigit(value.charAt(start + 1)) && isDigit(value.charAt(start + 2))
    && isDigit(value.charAt(start + 4)) && isDigit(value.charAt(start + 5));
}

function isDigit(value: string | undefined): boolean {
  return value !== undefined && value >= '0' && value <= '9';
}
