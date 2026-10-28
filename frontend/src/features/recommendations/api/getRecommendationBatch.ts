import { apiRequest } from '../../../api/client';
import type { RecommendationBatch } from '../models/recommendation';
export function getRecommendationBatch(
  batchId: string,
  signal?: AbortSignal,
): Promise<RecommendationBatch> {
  return apiRequest(
    `/api/v1/recommendations/${encodeURIComponent(batchId)}`,
    signal ? { signal } : {},
  );
}
