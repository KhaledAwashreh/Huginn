import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function markRecommendationNotRelevant(
  recommendationId: string,
  request: components['schemas']['MarkRecommendationNotRelevantRequest'],
): Promise<components['schemas']['MarkRecommendationNotRelevantResponse']> {
  return apiRequest(
    `/api/v1/recommendations/${encodeURIComponent(recommendationId)}/not-relevant`,
    { method: 'POST', body: request },
  );
}
