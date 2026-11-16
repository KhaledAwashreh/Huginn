import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function generateRecommendations(
  strategyId: string,
  limit = 10,
): Promise<components['schemas']['GenerateRecommendationsResponse']> {
  return apiRequest('/api/v1/recommendations', {
    method: 'POST',
    body: { strategy_id: strategyId, limit },
  });
}
