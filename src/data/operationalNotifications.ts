import type { Prediction } from './predictionsClient';

const priorityRank: Record<Prediction['priority'], number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

export type OperationalNotification = Prediction & { probability: number; qualityStatus: 'passed' };

export function buildOperationalNotifications(
  predictions: Prediction[],
  now: number = Date.now(),
): OperationalNotification[] {
  return predictions
    .filter((prediction): prediction is OperationalNotification => (
      (prediction.evidenceTier === 'validated' || prediction.evidenceTier === 'proxy')
      && prediction.qualityStatus === 'passed'
      && prediction.probability !== null
      && prediction.status !== 'rejected'
      && prediction.status !== 'resolved'
      && Date.parse(prediction.predictedAt) + prediction.horizonHours * 3_600_000 > now
    ))
    .toSorted((left, right) => priorityRank[right.priority] - priorityRank[left.priority]
      || Date.parse(right.predictedAt) - Date.parse(left.predictedAt));
}
export async function predictionIncidentId(predictionId: string): Promise<string> {
  const bytes = new TextEncoder().encode(`forpost-prediction:${predictionId}`);
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}
