import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function recordRecommendationFeedback(
  recommendationId: string,
  request: components['schemas']['RecordRecommendationFeedbackRequest'],
): Promise<components['schemas']['RecordRecommendationFeedbackResponse']> {
  return apiRequest(`/api/v1/recommendations/${encodeURIComponent(recommendationId)}/feedback`, {
    method: 'POST',
    body: request,
  });
}
