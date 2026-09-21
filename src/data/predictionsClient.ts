export type PredictionType = 'sensor_failure' | 'fire_risk' | 'unauthorized_access' | 'infrastructure_wear';
export type EvidenceTier = 'validated' | 'proxy' | 'anomaly' | 'scenario';
export type PredictionPriority = 'low' | 'medium' | 'high' | 'critical';
export type PredictionStatus = 'new' | 'acknowledged' | 'confirmed' | 'rejected' | 'escalated' | 'resolved';

export type Prediction = {
  id: string;
  entityType: 'sensor' | 'location';
  entityId: string;
  predictionType: PredictionType;
  probability: number | null;
  anomalyScore: number | null;
  evidenceTier: EvidenceTier;
  calibrated: boolean;
  provenance: 'observed' | 'derived' | 'simulated';
  confidence: { lower: number; upper: number } | null;
  modelMetrics: {
    precision: number;
    recall: number;
    f1: number;
    prAuc: number;
    brierScore: number;
  } | null;
  qualityStatus: 'passed' | 'limited';
  limitations: string[];
  predictedAt: string;
  horizonHours: number;
  modelVersion: string;
  factors: Array<{ factor: string; weight: number; description: string }>;
  recommendedAction: string;
  priority: PredictionPriority;
  status: PredictionStatus;
};

export type PredictionFeed = {
  status: 'ready' | 'unavailable';
  availableTypes: PredictionType[];
  predictions: Prediction[];
};

export async function fetchPredictions(
  fetcher: typeof globalThis.fetch = globalThis.fetch,
): Promise<Prediction[]> {
  return (await fetchPredictionFeed(fetcher)).predictions;
}

export async function fetchPredictionFeed(
  fetcher: typeof globalThis.fetch = globalThis.fetch,
): Promise<PredictionFeed> {
  try {
    const response = await fetcher('/api/predictions', { cache: 'no-store' });
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
      return unavailableFeed();
    }
    const payload: unknown = await response.json();
    if (!isRecord(payload)
      || !Array.isArray(payload.predictions)
      || !Array.isArray(payload.available_types)
      || payload.available_types.length === 0
      || !payload.available_types.every(isPredictionType)) return unavailableFeed();
    const availableTypes = [...new Set(payload.available_types)] as PredictionType[];
    if (availableTypes.length !== payload.available_types.length) return unavailableFeed();
    const predictions = payload.predictions.map(parsePrediction);
    if (predictions.some((item) => item === null)) return unavailableFeed();
    const typedPredictions = predictions as Prediction[];
    if (typedPredictions.some((item) => !availableTypes.includes(item.predictionType))) {
      return unavailableFeed();
    }
    return { status: 'ready', availableTypes, predictions: typedPredictions };
  } catch {
    return unavailableFeed();
  }
}

function unavailableFeed(): PredictionFeed {
  return { status: 'unavailable', availableTypes: [], predictions: [] };
}

function parsePrediction(value: unknown): Prediction | null {
  if (!isRecord(value)
    || typeof value.id !== 'string'
    || (value.entity_type !== 'sensor' && value.entity_type !== 'location')
    || typeof value.entity_id !== 'string'
    || !isPredictionType(value.prediction_type)
    || !isEvidenceTier(value.evidence_tier)
    || typeof value.calibrated !== 'boolean'
    || !isProvenance(value.provenance)
    || !isQualityStatus(value.quality_status)
    || !Array.isArray(value.limitations)
    || !value.limitations.every((item) => typeof item === 'string')
    || !isTimestampWithTimezone(value.predicted_at)
    || typeof value.horizon_hours !== 'number'
    || !Number.isInteger(value.horizon_hours) || value.horizon_hours <= 0
    || typeof value.model_version !== 'string'
    || !Array.isArray(value.factors)
    || typeof value.recommended_action !== 'string'
    || !isPriority(value.priority)
    || !isPredictionStatus(value.status)) return null;

  const probability = unitNumberOrNull(value.probability);
  const anomalyScore = unitNumberOrNull(value.anomaly_score);
  const confidence = parseConfidence(value.confidence);
  const modelMetrics = parseMetrics(value.model_metrics);
  const factors = value.factors.map(parseFactor);
  if (probability === undefined || anomalyScore === undefined || confidence === undefined
    || modelMetrics === undefined || factors.some((item) => item === null)) return null;
  if ((value.evidence_tier === 'validated' || value.evidence_tier === 'proxy')
    && (probability === null || !value.calibrated || modelMetrics === null)) return null;
  if (value.evidence_tier === 'anomaly' && (probability !== null || anomalyScore === null || value.calibrated)) return null;
  if (value.evidence_tier === 'scenario'
    && (value.provenance !== 'simulated' || probability !== null || anomalyScore !== null || value.calibrated)) return null;
  const typedFactors = factors as Prediction['factors'];
  if (!typedFactors.every((item, index) => index === 0
    || Math.abs(typedFactors[index - 1].weight) >= Math.abs(item.weight))) return null;

  return {
    id: value.id,
    entityType: value.entity_type,
    entityId: value.entity_id,
    predictionType: value.prediction_type,
    probability,
    anomalyScore,
    evidenceTier: value.evidence_tier,
    calibrated: value.calibrated,
    provenance: value.provenance as Prediction['provenance'],
    confidence,
    modelMetrics,
    qualityStatus: value.quality_status as Prediction['qualityStatus'],
    limitations: value.limitations,
    predictedAt: value.predicted_at,
    horizonHours: value.horizon_hours,
    modelVersion: value.model_version,
    factors: typedFactors,
    recommendedAction: value.recommended_action,
    priority: value.priority,
    status: value.status,
  };
}

function parseFactor(value: unknown): Prediction['factors'][number] | null {
  return isRecord(value) && typeof value.factor === 'string' && typeof value.weight === 'number'
    && Number.isFinite(value.weight) && typeof value.description === 'string'
    ? { factor: value.factor, weight: value.weight, description: value.description }
    : null;
}

function parseConfidence(value: unknown): Prediction['confidence'] | undefined {
  if (value === null) return null;
  if (!isRecord(value)) return undefined;
  const lower = unitNumberOrNull(value.lower);
  const upper = unitNumberOrNull(value.upper);
  return lower === null || lower === undefined || upper === null || upper === undefined || lower > upper
    ? undefined : { lower, upper };
}

function parseMetrics(value: unknown): Prediction['modelMetrics'] | undefined {
  if (value === null) return null;
  if (!isRecord(value)) return undefined;
  const values = [
    unitNumberOrNull(value.precision),
    unitNumberOrNull(value.recall),
    unitNumberOrNull(value.f1),
    unitNumberOrNull(value.pr_auc),
    unitNumberOrNull(value.brier_score),
  ];
  if (values.some((item) => item === null || item === undefined)) return undefined;
  const [precision, recall, f1, prAuc, brierScore] = values as number[];
  return { precision, recall, f1, prAuc, brierScore };
}

function unitNumberOrNull(value: unknown): number | null | undefined {
  if (value === null) return null;
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
    ? value : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isPredictionType(value: unknown): value is PredictionType {
  return typeof value === 'string'
    && ['sensor_failure', 'fire_risk', 'unauthorized_access', 'infrastructure_wear'].includes(value);
}

function isEvidenceTier(value: unknown): value is EvidenceTier {
  return typeof value === 'string'
    && ['validated', 'proxy', 'anomaly', 'scenario'].includes(value);
}

function isProvenance(value: unknown): value is Prediction['provenance'] {
  return typeof value === 'string' && ['observed', 'derived', 'simulated'].includes(value);
}

function isQualityStatus(value: unknown): value is Prediction['qualityStatus'] {
  return typeof value === 'string' && ['passed', 'limited'].includes(value);
}

function isPriority(value: unknown): value is PredictionPriority {
  return typeof value === 'string' && ['low', 'medium', 'high', 'critical'].includes(value);
}

function isPredictionStatus(value: unknown): value is PredictionStatus {
  return typeof value === 'string'
    && ['new', 'acknowledged', 'confirmed', 'rejected', 'escalated', 'resolved'].includes(value);
}

function isTimestampWithTimezone(value: unknown): value is string {
  return typeof value === 'string'
    && /(Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value));
}
