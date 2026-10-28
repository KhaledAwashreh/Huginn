import { apiRequest } from '../../../api/client';
import type { RecommendationFeedback } from '../models/recommendationFeedback';
export function listRecommendationFeedback(
  batchId: string,
  signal?: AbortSignal,
): Promise<RecommendationFeedback[]> {
  return apiRequest(
    `/api/v1/recommendations/${encodeURIComponent(batchId)}/feedback`,
    signal ? { signal } : {},
  );
}
