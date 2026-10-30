import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';
import type { RecommendationFeedback } from '../models/recommendationFeedback';
export function saveRecommendationFeedback(
  batchId: string,
  draft: components['schemas']['RecommendationFeedbackRequest'],
): Promise<RecommendationFeedback> {
  return apiRequest(`/api/v1/recommendations/${encodeURIComponent(batchId)}/feedback`, {
    method: 'POST',
    body: draft,
  });
}
