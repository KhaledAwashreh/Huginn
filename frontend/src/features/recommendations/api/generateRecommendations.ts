import { apiRequest } from '../../../api/client';
import type { RecommendationBatch } from '../models/recommendation';
export function generateRecommendations(
  strategyId: string,
  limit = 10,
): Promise<RecommendationBatch> {
  return apiRequest('/api/v1/recommendations', {
    method: 'POST',
    body: { strategy_id: strategyId, limit },
  });
}
