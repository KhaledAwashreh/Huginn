import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function laterRecommendation(
  recommendationId: string,
  request: components['schemas']['LaterRecommendationRequest'],
): Promise<components['schemas']['LaterRecommendationResponse']> {
  return apiRequest(`/api/v1/recommendations/${encodeURIComponent(recommendationId)}/later`, {
    method: 'POST',
    body: request,
  });
}
