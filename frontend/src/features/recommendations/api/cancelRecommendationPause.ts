import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function cancelRecommendationPause(
  blockId: string,
  request: components['schemas']['ClearRecommendationSuppressionRequest'],
): Promise<components['schemas']['ClearRecommendationSuppressionResponse']> {
  return apiRequest(`/api/v1/suppressions/${encodeURIComponent(blockId)}/cancel-pause`, {
    method: 'POST',
    body: request,
  });
}
