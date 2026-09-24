export type DemoProfile = 'district-dispatcher' | 'central-dispatcher' | 'technician' | 'admin';
export type IncidentStatus = 'new' | 'in_review' | 'crew_dispatch' | 'false_alarm' | 'confirmed_incident' | 'closed';
export type Priority = 'low' | 'medium' | 'high' | 'critical';
export type PredictionDecision = 'confirmed' | 'rejected' | 'escalated';

export type DemoSession = {
  active: true;
  profile?: DemoProfile;
  csrfToken: string;
  provenance: 'simulated';
};

export type IncidentDecision = {
  decisionId: string;
  incidentId: string;
  status: IncidentStatus;
  reason: string;
  actorId: string;
  createdAt: string;
  correctsDecisionId: string | null;
  provenance: 'simulated';
};

export type PredictionDecisionReceipt = {
  status: 'recorded';
  predictionId: string;
  auditRecordId: number;
};

export type ServiceRequestDraft = {
  draftId: string;
  incidentId: string;
  targetId: string;
  category: string;
  priority: Priority;
  recommendedAction: string;
  dueAt: string;
  authorId: string;
  createdAt: string;
  provenance: 'simulated';
};

export type TopologyFeature = {
  type: 'Feature';
  id: string;
  geometry: { type: 'MultiLineString'; coordinates: number[][][] };
  properties: {
    objectId: string;
    parentId: string | null;
    objectKind: string;
    dispatcherName: string;
    geometrySource: 'synthetic';
    provenance: 'derived';
    coordinateProvenance: 'simulated';
  };
};

export type TopologyFeatureCollection = {
  type: 'FeatureCollection';
  features: TopologyFeature[];
  metadata: {
    title: 'Схема объектов';
    geometrySource: 'synthetic';
    coordinateProvenance: 'simulated';
  };
};

export class OperationsClientError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'OperationsClientError';
  }
}

type Fetcher = typeof globalThis.fetch;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).sort().join('\0') === [...keys].sort().join('\0');
}

function isTimestamp(value: unknown): value is string {
  if (typeof value !== 'string' || value.length < 20 || value.length > 35 || !value.includes('T')) {
    return false;
  }
  const timezoneMarker = value.endsWith('Z')
    || value.lastIndexOf('+') > value.indexOf('T')
    || value.lastIndexOf('-') > value.indexOf('T');
  return timezoneMarker && !Number.isNaN(Date.parse(value));
}

async function payloadOrError(response: Response): Promise<unknown> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new OperationsClientError('Сервис вернул некорректный ответ', 502);
  }
  if (!response.ok) {
    let message = 'Операция не выполнена';
    if (isRecord(payload)) {
      if (typeof payload.error === 'string') message = payload.error;
      else if (typeof payload.detail === 'string') message = payload.detail;
      else if (isRecord(payload.detail) && typeof payload.detail.message === 'string') {
        message = payload.detail.message;
      }
    }
    throw new OperationsClientError(message.slice(0, 500), response.status);
  }
  return payload;
}

function isDemoSession(value: unknown): value is DemoSession {
  if (!isRecord(value)) return false;
  const keys = Object.keys(value);
  const validKeys = keys.length === 4
    ? ['active', 'profile', 'csrfToken', 'provenance']
    : ['active', 'csrfToken', 'provenance'];
  return hasExactKeys(value, validKeys)
    && value.active === true
    && (value.profile === undefined || ['district-dispatcher', 'central-dispatcher', 'technician', 'admin'].includes(String(value.profile)))
    && typeof value.csrfToken === 'string'
    && value.csrfToken.length >= 32
    && value.provenance === 'simulated';
}

function isIncidentDecision(value: unknown): value is IncidentDecision {
  return isRecord(value)
    && hasExactKeys(value, ['decisionId', 'incidentId', 'status', 'reason', 'actorId', 'createdAt', 'correctsDecisionId', 'provenance'])
    && typeof value.decisionId === 'string'
    && typeof value.incidentId === 'string'
    && /^[a-f0-9]{64}$/.test(value.incidentId)
    && ['new', 'in_review', 'crew_dispatch', 'false_alarm', 'confirmed_incident', 'closed'].includes(String(value.status))
    && typeof value.reason === 'string'
    && typeof value.actorId === 'string'
    && isTimestamp(value.createdAt)
    && (value.correctsDecisionId === null || typeof value.correctsDecisionId === 'string')
    && value.provenance === 'simulated';
}

function parsePredictionDecisionReceipt(
  value: unknown,
  predictionId: string,
): PredictionDecisionReceipt | null {
  if (!isRecord(value)
    || !hasExactKeys(value, ['status', 'prediction_id', 'audit_record_id'])
    || value.status !== 'recorded'
    || value.prediction_id !== predictionId
    || typeof value.audit_record_id !== 'number'
    || !Number.isSafeInteger(value.audit_record_id)
    || value.audit_record_id < 0) return null;
  return { status: 'recorded', predictionId, auditRecordId: value.audit_record_id };
}

function isServiceDraft(value: unknown): value is ServiceRequestDraft {
  return isRecord(value)
    && hasExactKeys(value, ['draftId', 'incidentId', 'targetId', 'category', 'priority', 'recommendedAction', 'dueAt', 'authorId', 'createdAt', 'provenance'])
    && typeof value.draftId === 'string'
    && typeof value.incidentId === 'string'
    && /^[a-f0-9]{64}$/.test(value.incidentId)
    && typeof value.targetId === 'string'
    && typeof value.category === 'string'
    && ['low', 'medium', 'high', 'critical'].includes(String(value.priority))
    && typeof value.recommendedAction === 'string'
    && isTimestamp(value.dueAt)
    && typeof value.authorId === 'string'
    && isTimestamp(value.createdAt)
    && value.provenance === 'simulated';
}

function isCoordinates(value: unknown): value is number[][][] {
  return Array.isArray(value) && value.length > 0 && value.every((line) => (
    Array.isArray(line) && line.length >= 2 && line.every((position) => (
      Array.isArray(position)
      && position.length === 2
      && position.every((coordinate) => typeof coordinate === 'number' && Number.isFinite(coordinate) && Math.abs(coordinate) <= 1_000_000)
    ))
  ));
}

function isTopologyFeature(value: unknown): value is TopologyFeature {
  if (!isRecord(value) || !hasExactKeys(value, ['type', 'id', 'geometry', 'properties'])) return false;
  if (!isRecord(value.geometry) || !hasExactKeys(value.geometry, ['type', 'coordinates'])) return false;
  if (!isRecord(value.properties) || !hasExactKeys(value.properties, [
    'objectId', 'parentId', 'objectKind', 'dispatcherName', 'geometrySource', 'provenance', 'coordinateProvenance',
  ])) return false;
  return value.type === 'Feature'
    && typeof value.id === 'string'
    && value.geometry.type === 'MultiLineString'
    && isCoordinates(value.geometry.coordinates)
    && value.properties.objectId === value.id
    && (value.properties.parentId === null || typeof value.properties.parentId === 'string')
    && typeof value.properties.objectKind === 'string'
    && typeof value.properties.dispatcherName === 'string'
    && value.properties.geometrySource === 'synthetic'
    && value.properties.provenance === 'derived'
    && value.properties.coordinateProvenance === 'simulated';
}

function isTopology(value: unknown): value is TopologyFeatureCollection {
  if (!isRecord(value) || !hasExactKeys(value, ['type', 'features', 'metadata'])) return false;
  if (!isRecord(value.metadata) || !hasExactKeys(value.metadata, ['title', 'geometrySource', 'coordinateProvenance'])) return false;
  return value.type === 'FeatureCollection'
    && Array.isArray(value.features)
    && value.features.length <= 50_000
    && value.features.every(isTopologyFeature)
    && value.metadata.title === 'Схема объектов'
    && value.metadata.geometrySource === 'synthetic'
    && value.metadata.coordinateProvenance === 'simulated';
}

export async function startDemoSession(
  profile: DemoProfile,
  fetcher: Fetcher = globalThis.fetch,
): Promise<DemoSession> {
  const response = await fetcher('/api/demo-session', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile }),
  });
  const payload = await payloadOrError(response);
  if (!isDemoSession(payload)) throw new OperationsClientError('Некорректный ответ demo-сессии', 502);
  return payload;
}

export async function getDemoSession(fetcher: Fetcher = globalThis.fetch): Promise<DemoSession | null> {
  const payload = await payloadOrError(await fetcher('/api/demo-session', {
    cache: 'no-store',
    credentials: 'same-origin',
  }));
  if (isRecord(payload)
    && hasExactKeys(payload, ['active', 'provenance'])
    && payload.active === false
    && payload.provenance === 'unavailable') {
    return null;
  }
  if (!isDemoSession(payload)) throw new OperationsClientError('Некорректное состояние demo-сессии', 502);
  return payload;
}

export async function recordIncidentDecision(
  incidentId: string,
  decision: { status: IncidentStatus; reason: string; correctsDecisionId?: string },
  csrfToken: string,
  idempotencyKey: string,
  fetcher: Fetcher = globalThis.fetch,
): Promise<IncidentDecision> {
  const response = await fetcher(`/api/incidents/${incidentId}/decisions`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
      'X-Forpost-CSRF': csrfToken,
    },
    body: JSON.stringify(decision),
  });
  const payload = await payloadOrError(response);
  if (!isIncidentDecision(payload)) throw new OperationsClientError('Некорректный ответ решения', 502);
  return payload;
}

export async function recordPredictionDecision(
  predictionId: string,
  decision: { decision: PredictionDecision; reason: string },
  csrfToken: string,
  fetcher: Fetcher = globalThis.fetch,
): Promise<PredictionDecisionReceipt> {
  const response = await fetcher(`/api/predictions/${encodeURIComponent(predictionId)}/decisions`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Forpost-CSRF': csrfToken },
    body: JSON.stringify(decision),
  });
  const payload = await payloadOrError(response);
  const receipt = parsePredictionDecisionReceipt(payload, predictionId);
  if (receipt === null) throw new OperationsClientError('Некорректное подтверждение решения по прогнозу', 502);
  return receipt;
}

export async function fetchIncidentDecisions(
  incidentId: string,
  fetcher: Fetcher = globalThis.fetch,
): Promise<IncidentDecision[]> {
  const payload = await payloadOrError(await fetcher(`/api/incidents/${incidentId}/decisions`, { cache: 'no-store' }));
  if (!Array.isArray(payload) || !payload.every(isIncidentDecision)) {
    throw new OperationsClientError('Некорректная история решений', 502);
  }
  return payload;
}

export async function fetchServiceDrafts(fetcher: Fetcher = globalThis.fetch): Promise<ServiceRequestDraft[]> {
  const payload = await payloadOrError(await fetcher('/api/service-request-drafts', { cache: 'no-store' }));
  if (!Array.isArray(payload) || !payload.every(isServiceDraft)) {
    throw new OperationsClientError('Некорректный список черновиков', 502);
  }
  return payload;
}

export async function createServiceDraft(
  draft: Omit<ServiceRequestDraft, 'draftId' | 'authorId' | 'createdAt' | 'provenance'>,
  csrfToken: string,
  fetcher: Fetcher = globalThis.fetch,
): Promise<ServiceRequestDraft> {
  const response = await fetcher('/api/service-request-drafts', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Forpost-CSRF': csrfToken },
    body: JSON.stringify(draft),
  });
  const payload = await payloadOrError(response);
  if (!isServiceDraft(payload)) throw new OperationsClientError('Некорректный ответ черновика', 502);
  return payload;
}

export async function createPredictionServiceDraft(
  predictionId: string,
  csrfToken: string,
  fetcher: Fetcher = globalThis.fetch,
): Promise<ServiceRequestDraft> {
  const response = await fetcher(
    `/api/predictions/${encodeURIComponent(predictionId)}/service-request-drafts`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Forpost-CSRF': csrfToken },
      body: JSON.stringify({}),
    },
  );
  const payload = await payloadOrError(response);
  if (!isServiceDraft(payload)) {
    throw new OperationsClientError('Некорректный ответ черновика по прогнозу', 502);
  }
  return payload;
}

export async function fetchTopology(fetcher: Fetcher = globalThis.fetch): Promise<TopologyFeatureCollection> {
  const payload = await payloadOrError(await fetcher('/api/topology', { cache: 'no-store' }));
  if (!isTopology(payload)) throw new OperationsClientError('Некорректная схема объектов', 502);
  return payload;
}
