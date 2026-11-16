import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function reverseRecommendationRejection(
  blockId: string,
  request: components['schemas']['ClearRecommendationSuppressionRequest'],
): Promise<components['schemas']['ClearRecommendationSuppressionResponse']> {
  return apiRequest(`/api/v1/suppressions/${encodeURIComponent(blockId)}/reverse-rejection`, {
    method: 'POST',
    body: request,
  });
}
