export const MAX_OBSERVED_EVENTS = 500;

export type SourceAvailability = {
  events: boolean;
  channels: boolean;
  objects: boolean;
  access_events: boolean;
  maintenance_history: boolean;
  ml_predictions: boolean;
  work_permits: boolean;
};

export type Provenance = 'observed' | 'derived' | 'simulated' | 'unavailable';

export type DataQuality = {
  builtAt: string;
  latestObservedAt: string | null;
  eventCount: number;
  skippedTimestampCount: number;
  technicalAnomalyCount: number;
  unmappedChannelCount: number;
  objectLinkAvailable: boolean;
  freshness: 'fresh' | 'stale' | 'historical';
};

export type LocalSituationChannel = {
  channelId: string;
  engineeringSystemType: string;
  sensorType: string;
  engineeringSystemTag: string;
  sensorName: string;
  objectId: string | null;
};

export type LocalSituationObject = {
  objectId: string;
  hierarchyLevel: string;
  parentId: string | null;
  objectKind: string;
  dispatcherName: string;
};

export type LocalSituationEvent = {
  canonicalId: string;
  eventId: string;
  channelId: string;
  recordedAt: string;
  isAlarm: boolean | null;
  sensorValue: string;
  qualityCode: 'valid' | 'technical_anomaly' | 'alarm_with_technical_value' | 'monitoring_system_migration';
  analysisEligible: boolean;
  provenance: 'observed';
};

export type LocalSituationSnapshot = {
  sourceAvailability: SourceAvailability;
  dataQuality: DataQuality;
  channels: LocalSituationChannel[];
  objects: LocalSituationObject[];
  events: LocalSituationEvent[];
};

const SNAPSHOT_KEYS = [
  'sourceAvailability',
  'dataQuality',
  'channels',
  'objects',
  'events',
] as const;

const LEGACY_SOURCE_METADATA_KEYS = [
  'journalFileCount',
  'selectedJournalFileCount',
  'scannedEventCount',
  'skippedEventCount',
  'channelCount',
  'objectCount',
  'latestObservedAt',
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const allowed = [...expected].sort();
  return actual.length === allowed.length && actual.join('\u0000') === allowed.join('\u0000');
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean';
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 0;
}

function isUtcTimestamp(value: unknown): value is string {
  return isString(value) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)
    && !Number.isNaN(Date.parse(value));
}

export function isObservedTimestamp(value: unknown): value is string {
  if (!isString(value)) {
    return false;
  }

  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/.exec(value);
  if (match === null) {
    return false;
  }

  const [year, month, day, hour, minute, second] = match.slice(1).map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day
    && parsed.getUTCHours() === hour
    && parsed.getUTCMinutes() === minute
    && parsed.getUTCSeconds() === second;
}

function isSourceAvailability(value: unknown): value is SourceAvailability {
  if (!isRecord(value) || !hasExactKeys(value, [
    'events',
    'channels',
    'objects',
    'access_events',
    'maintenance_history',
    'ml_predictions',
    'work_permits',
  ])) {
    return false;
  }

  return Object.values(value).every(isBoolean);
}

function isDataQuality(value: unknown): value is DataQuality {
  if (!isRecord(value) || !hasExactKeys(value, [
    'builtAt',
    'latestObservedAt',
    'eventCount',
    'skippedTimestampCount',
    'technicalAnomalyCount',
    'unmappedChannelCount',
    'objectLinkAvailable',
    'freshness',
  ])) {
    return false;
  }

  return isUtcTimestamp(value.builtAt)
    && (value.latestObservedAt === null || isObservedTimestamp(value.latestObservedAt))
    && isNonNegativeInteger(value.eventCount)
    && isNonNegativeInteger(value.skippedTimestampCount)
    && isNonNegativeInteger(value.technicalAnomalyCount)
    && isNonNegativeInteger(value.unmappedChannelCount)
    && isBoolean(value.objectLinkAvailable)
    && ['fresh', 'stale', 'historical'].includes(String(value.freshness));
}

function isChannel(value: unknown): value is LocalSituationChannel {
  return isRecord(value) && hasExactKeys(value, [
    'channelId',
    'engineeringSystemType',
    'sensorType',
    'engineeringSystemTag',
    'sensorName',
    'objectId',
  ])
    && isString(value.channelId)
    && isString(value.engineeringSystemType)
    && isString(value.sensorType)
    && isString(value.engineeringSystemTag)
    && isString(value.sensorName)
    && (value.objectId === null || isString(value.objectId));
}

function isObject(value: unknown): value is LocalSituationObject {
  if (!isRecord(value) || !hasExactKeys(value, [
    'objectId',
    'hierarchyLevel',
    'parentId',
    'objectKind',
    'dispatcherName',
  ])) {
    return false;
  }

  return isString(value.objectId)
    && isString(value.hierarchyLevel)
    && (value.parentId === null || isString(value.parentId))
    && isString(value.objectKind)
    && isString(value.dispatcherName);
}

function isEvent(value: unknown): value is LocalSituationEvent {
  if (!isRecord(value) || !hasExactKeys(value, [
    'eventId',
    'canonicalId',
    'channelId',
    'recordedAt',
    'isAlarm',
    'sensorValue',
    'qualityCode',
    'analysisEligible',
    'provenance',
  ])) {
    return false;
  }

  return isString(value.canonicalId)
    && /^[a-f0-9]{64}$/.test(value.canonicalId)
    && isString(value.eventId)
    && isString(value.channelId)
    && isObservedTimestamp(value.recordedAt)
    && (value.isAlarm === null || isBoolean(value.isAlarm))
    && isString(value.sensorValue)
    && ['valid', 'technical_anomaly', 'alarm_with_technical_value', 'monitoring_system_migration']
      .includes(String(value.qualityCode))
    && isBoolean(value.analysisEligible)
    && value.provenance === 'observed';
}

export function isLocalSituationSnapshot(value: unknown): value is LocalSituationSnapshot {
  if (!isRecord(value) || !hasExactKeys(value, SNAPSHOT_KEYS)) {
    return false;
  }

  if (!isSourceAvailability(value.sourceAvailability)
    || !isDataQuality(value.dataQuality)) {
    return false;
  }

  if (!Array.isArray(value.channels)
    || !value.channels.every(isChannel)
    || !Array.isArray(value.objects)
    || !value.objects.every(isObject)
    || !Array.isArray(value.events)
    || value.events.length > MAX_OBSERVED_EVENTS
    || !value.events.every(isEvent)) {
    return false;
  }

  const unmappedChannels = value.channels.filter((channel) => channel.objectId === null).length;
  return value.dataQuality.eventCount === value.events.length
    && value.dataQuality.technicalAnomalyCount <= value.events.length
    && value.dataQuality.unmappedChannelCount === unmappedChannels
    && (value.dataQuality.objectLinkAvailable || unmappedChannels === value.channels.length);
}

function isLegacySourceMetadata(value: unknown): boolean {
  if (!isRecord(value) || !hasExactKeys(value, LEGACY_SOURCE_METADATA_KEYS)) {
    return false;
  }

  return isNonNegativeInteger(value.journalFileCount)
    && isNonNegativeInteger(value.selectedJournalFileCount)
    && isNonNegativeInteger(value.scannedEventCount)
    && isNonNegativeInteger(value.skippedEventCount)
    && isNonNegativeInteger(value.channelCount)
    && isNonNegativeInteger(value.objectCount)
    && (value.latestObservedAt === null || isObservedTimestamp(value.latestObservedAt));
}

/**
 * Нормализует только ранее выпущенный локальный конверт снимка. Служебные
 * метаданные валидируются и удаляются до возврата данных через публичный API.
 */
export function normalizeStoredLocalSituationSnapshot(
  value: unknown,
): LocalSituationSnapshot | null {
  if (isLocalSituationSnapshot(value)) {
    return value;
  }

  if (!isRecord(value)
    || !hasExactKeys(value, [...SNAPSHOT_KEYS, 'sourceMetadata'])
    || !isLegacySourceMetadata(value.sourceMetadata)) {
    return null;
  }

  const snapshotCandidate: unknown = {
    sourceAvailability: value.sourceAvailability,
    dataQuality: value.dataQuality,
    channels: value.channels,
    objects: value.objects,
    events: value.events,
  };

  return isLocalSituationSnapshot(snapshotCandidate) ? snapshotCandidate : null;
}
