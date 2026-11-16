import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function saveRecommendation(
  recommendationId: string,
  request: components['schemas']['SaveRecommendationRequest'],
): Promise<components['schemas']['SaveRecommendationResponse']> {
  return apiRequest(`/api/v1/recommendations/${encodeURIComponent(recommendationId)}/save`, {
    method: 'POST',
    body: request,
  });
}
