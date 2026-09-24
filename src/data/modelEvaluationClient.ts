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
  | 'logistic_regression_sigmoid'
  | 'catboost_isotonic'
  | 'catboost_sigmoid'
  | 'lightgbm_isotonic'
  | 'lightgbm_sigmoid';

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

export type OperatingProfile = {
  threshold: number;
  precision: number;
  recall: number;
  alertRate: number;
};

export type ConfidenceInterval = {
  lower: number;
  upper: number;
  level: 0.95;
  method: 'student_t_across_rolling_folds';
};

export type RollingFold = {
  index: number;
  trainRows: number;
  calibrationRows: number;
  validationRows: number;
  threshold: number;
  metrics: ModelMetrics;
};

export type OperatingProfiles = {
  highPrecision: OperatingProfile;
  balanced: OperatingProfile;
  highRecall: OperatingProfile;
};

export type ValidationConfidenceIntervals = Record<keyof ModelMetrics, ConfidenceInterval>;

export type ModelEvaluation = {
  formatVersion: 2;
  task: 'sensor_failure';
  version: string;
  status: EvaluationStatus;
  evidenceTier: 'proxy';
  labelStrategy: 'cadence_adjusted_silence_horizon_proxy_v2';
  taskSemantics: 'risk_of_unexpected_telemetry_silence_within_horizon';
  featureSchemaVersion: '6' | null;
  configSha256: string | null;
  libraryVersions: Record<string, string>;
  rollingFolds: RollingFold[];
  operatingProfiles: OperatingProfiles | null;
  validationConfidenceIntervals: ValidationConfidenceIntervals | null;
  horizonHours: number | null;
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
  | { status: 'unauthenticated' }
  | { status: 'unavailable' };

const metricKeys = ['precision', 'recall', 'f1', 'pr_auc', 'roc_auc', 'brier_score', 'expected_calibration_error', 'alert_rate'] as const;
const thresholdKeys = ['minimum_precision', 'minimum_recall', 'maximum_alert_rate', 'maximum_expected_calibration_error', 'maximum_brier_score', 'minimum_baseline_pr_auc_delta'] as const;
const splitKeys = ['fit', 'calibration', 'validation', 'test'] as const;
const foldKeys = ['index', 'train_rows', 'calibration_rows', 'validation_rows', 'threshold', 'metrics'] as const;
const profileKeys = ['threshold', 'precision', 'recall', 'alert_rate'] as const;
const profileNames = ['high_precision', 'balanced', 'high_recall'] as const;
const confidenceKeys = ['lower', 'upper', 'level', 'method'] as const;
const libraryNames = ['numpy', 'pandas', 'scikit-learn', 'skops', 'catboost', 'lightgbm'] as const;
const reportKeys = ['format_version', 'task', 'version', 'status', 'evidence_tier', 'label_strategy', 'task_semantics', 'feature_schema_version', 'config_sha256', 'library_versions', 'rolling_folds', 'operating_profiles', 'validation_confidence_intervals', 'horizon_hours', 'created_at', 'reason_code', 'quality_thresholds', 'split_sizes', 'baseline_validation_pr_auc', 'validation_metrics', 'test_metrics', 'threshold', 'champion_name'] as const;
const reasonCodes: readonly EvaluationReasonCode[] = ['configuration_invalid', 'source_unavailable', 'dataset_unavailable', 'training_unavailable', 'validation_rejected', 'test_rejected', 'inference_unavailable', 'release_unavailable'];
const candidates: readonly CandidateName[] = ['extra_trees_isotonic', 'extra_trees_sigmoid', 'hist_gradient_boosting_isotonic', 'hist_gradient_boosting_sigmoid', 'logistic_regression_isotonic', 'logistic_regression_sigmoid', 'catboost_isotonic', 'catboost_sigmoid', 'lightgbm_isotonic', 'lightgbm_sigmoid'];

export async function fetchModelEvaluation(
  fetcher: typeof globalThis.fetch = globalThis.fetch,
): Promise<ModelEvaluationFeed> {
  try {
    const response = await fetcher('/api/model-evaluation', { cache: 'no-store', credentials: 'same-origin' });
    if (response.status === 401) return { status: 'unauthenticated' };
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
    || value.format_version !== 2
    || value.task !== 'sensor_failure'
    || !isVersion(value.version)
    || !isEvaluationStatus(value.status)
    || value.evidence_tier !== 'proxy'
    || value.label_strategy !== 'cadence_adjusted_silence_horizon_proxy_v2'
    || value.task_semantics !== 'risk_of_unexpected_telemetry_silence_within_horizon'
    || (value.feature_schema_version !== null && value.feature_schema_version !== '6')
    || !isSha256OrNull(value.config_sha256)
    || !isLibraryVersions(value.library_versions)
    || !isRollingFolds(value.rolling_folds)
    || !isOperatingProfiles(value.operating_profiles)
    || !isConfidenceIntervals(value.validation_confidence_intervals)
    || !isHorizonOrNull(value.horizon_hours)
    || !isTimestampWithTimezone(value.created_at)
    || !isReasonCodeOrNull(value.reason_code)
    || !isQualityThresholdsOrNull(value.quality_thresholds)
    || !isSplitSizesOrNull(value.split_sizes)
    || !isUnitNumberOrNull(value.baseline_validation_pr_auc)
    || !isMetricsOrNull(value.validation_metrics)
    || !isMetricsOrNull(value.test_metrics)
    || !isThresholdOrNull(value.threshold)
    || !isCandidateOrNull(value.champion_name)) return null;

  if (value.status === 'published' && (!allEvidencePresent(value) || value.reason_code !== null
    || !isCompleteValidationEvidence(value))) return null;
  if (value.status === 'rejected' && (value.reason_code === null || value.test_metrics !== null)) return null;

  return {
    formatVersion: 2,
    task: 'sensor_failure',
    version: value.version,
    status: value.status,
    evidenceTier: 'proxy',
    labelStrategy: 'cadence_adjusted_silence_horizon_proxy_v2',
    taskSemantics: 'risk_of_unexpected_telemetry_silence_within_horizon',
    featureSchemaVersion: value.feature_schema_version,
    configSha256: value.config_sha256,
    libraryVersions: value.library_versions,
    rollingFolds: mapRollingFolds(value.rolling_folds),
    operatingProfiles: mapOperatingProfiles(value.operating_profiles),
    validationConfidenceIntervals: mapConfidenceIntervals(value.validation_confidence_intervals),
    horizonHours: value.horizon_hours,
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
  return value.feature_schema_version !== null
    && value.config_sha256 !== null
    && value.quality_thresholds !== null
    && value.horizon_hours !== null
    && value.split_sizes !== null
    && value.baseline_validation_pr_auc !== null
    && value.validation_metrics !== null
    && value.test_metrics !== null
    && value.threshold !== null
    && value.champion_name !== null;
}

function isCompleteValidationEvidence(value: Record<string, unknown>): boolean {
  if (!isExactRecord(value.library_versions, libraryNames)
    || !Array.isArray(value.rolling_folds) || value.rolling_folds.length < 3
    || !isExactRecord(value.operating_profiles, profileNames)
    || !isExactRecord(value.validation_confidence_intervals, metricKeys)
    || !isExactRecord(value.split_sizes, splitKeys)
    || typeof value.threshold !== 'number') return false;
  const folds = value.rolling_folds as Array<Record<string, unknown>>;
  const balanced = (value.operating_profiles as Record<string, Record<string, unknown>>).balanced;
  return folds.every((fold, index) => fold.index === index + 1 && fold.threshold === value.threshold)
    && folds.reduce((sum, fold) => sum + Number(fold.validation_rows), 0) === value.split_sizes.validation
    && balanced.threshold === value.threshold;
}

function mapRollingFolds(value: unknown): RollingFold[] {
  if (!Array.isArray(value)) return [];
  return value.map((fold) => ({
    index: fold.index,
    trainRows: fold.train_rows,
    calibrationRows: fold.calibration_rows,
    validationRows: fold.validation_rows,
    threshold: fold.threshold,
    metrics: mapMetrics(fold.metrics) as ModelMetrics,
  }));
}

function mapOperatingProfiles(value: unknown): OperatingProfiles | null {
  if (!isExactRecord(value, profileNames)) return null;
  return {
    highPrecision: mapOperatingProfile(value.high_precision),
    balanced: mapOperatingProfile(value.balanced),
    highRecall: mapOperatingProfile(value.high_recall),
  };
}

function mapOperatingProfile(value: unknown): OperatingProfile {
  const profile = value as Record<string, number>;
  return { threshold: profile.threshold, precision: profile.precision, recall: profile.recall, alertRate: profile.alert_rate };
}

function mapConfidenceIntervals(value: unknown): ValidationConfidenceIntervals | null {
  if (!isExactRecord(value, metricKeys)) return null;
  return {
    precision: value.precision as ConfidenceInterval,
    recall: value.recall as ConfidenceInterval,
    f1: value.f1 as ConfidenceInterval,
    prAuc: value.pr_auc as ConfidenceInterval,
    rocAuc: value.roc_auc as ConfidenceInterval,
    brierScore: value.brier_score as ConfidenceInterval,
    expectedCalibrationError: value.expected_calibration_error as ConfidenceInterval,
    alertRate: value.alert_rate as ConfidenceInterval,
  };
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

function isSha256OrNull(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && /^[a-f0-9]{64}$/.test(value));
}

function isLibraryVersions(value: unknown): value is Record<string, string> {
  return isRecord(value) && Object.entries(value).every(([name, version]) => name.length > 0
    && name.length <= 128 && typeof version === 'string' && version.length > 0 && version.length <= 128);
}

function isRollingFolds(value: unknown): value is Array<Record<string, unknown>> {
  return Array.isArray(value) && value.length <= 20 && value.every((fold) => isExactRecord(fold, foldKeys)
    && isBoundedPositiveInteger(fold.index, 20)
    && isPositiveSafeInteger(fold.train_rows)
    && isPositiveSafeInteger(fold.calibration_rows)
    && isPositiveSafeInteger(fold.validation_rows)
    && isUnitNumber(fold.threshold)
    && isMetricsOrNull(fold.metrics) && fold.metrics !== null);
}

function isOperatingProfiles(value: unknown): value is Record<string, Record<string, number>> {
  return isRecord(value) && Object.keys(value).every((key) => profileNames.includes(key as typeof profileNames[number]))
    && Object.values(value).every((profile) => isExactRecord(profile, profileKeys)
      && isUnitNumber(profile.threshold) && isUnitNumber(profile.precision)
      && isUnitNumber(profile.recall) && isUnitNumber(profile.alert_rate));
}

function isConfidenceIntervals(value: unknown): value is Record<string, ConfidenceInterval> {
  return isRecord(value) && Object.keys(value).every((key) => metricKeys.includes(key as typeof metricKeys[number]))
    && Object.values(value).every((interval) => isExactRecord(interval, confidenceKeys)
      && isUnitNumber(interval.lower) && isUnitNumber(interval.upper) && interval.lower <= interval.upper
      && interval.level === 0.95 && interval.method === 'student_t_across_rolling_folds');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
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

function isBoundedPositiveInteger(value: unknown, maximum: number): value is number {
  return isPositiveSafeInteger(value) && value <= maximum;
}

function isHorizonOrNull(value: unknown): value is number | null {
  return value === null || (isPositiveSafeInteger(value) && value <= 8760);
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
  if (!(value[4] === '-' && value[7] === '-' && value[13] === ':' && value[16] === ':'
    && digitPositions.every((position) => isDigit(value.charAt(position)))
    && [...value.slice(20, timezoneStart)].every(isDigit))) return false;
  const year = numericPart(value, 0, 4);
  const month = numericPart(value, 5, 7);
  const day = numericPart(value, 8, 10);
  const hour = numericPart(value, 11, 13);
  const minute = numericPart(value, 14, 16);
  const second = numericPart(value, 17, 19);
  const timezoneHour = value.endsWith('Z') ? 0 : numericPart(value, timezoneStart + 1, timezoneStart + 3);
  const timezoneMinute = value.endsWith('Z') ? 0 : numericPart(value, timezoneStart + 4, timezoneStart + 6);
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth(year, month)
    && hour <= 23 && minute <= 59 && second <= 59
    && timezoneHour <= 23 && timezoneMinute <= 59
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

function numericPart(value: string, start: number, end: number): number {
  return Number(value.slice(start, end));
}

function daysInMonth(year: number, month: number): number {
  if (month === 2) return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28;
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}
