import { apiRequest } from '../../../api/client';
import type { RecommendationBatch } from '../models/recommendation';
export function getLatestRecommendations(
  strategyId: string,
  signal?: AbortSignal,
): Promise<RecommendationBatch> {
  return apiRequest(
    `/api/v1/recommendations/latest?${new URLSearchParams({ strategy_id: strategyId })}`,
    signal ? { signal } : {},
  );
}
