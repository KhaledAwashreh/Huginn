import { apiRequest } from '../../../api/client';
import type { RecommendationBatch } from '../models/recommendation';

export function listWeeklyMatches(
  offset = 0,
  signal?: AbortSignal,
): Promise<RecommendationBatch[]> {
  return apiRequest(
    `/api/v1/recommendations/weekly?${new URLSearchParams({ limit: '12', offset: String(offset) })}`,
    signal ? { signal } : {},
  );
}
