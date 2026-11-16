import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function getRecommendation(
  recommendationId: string,
  signal?: AbortSignal,
  assessmentRevisionId?: string,
): Promise<components['schemas']['RecommendationResponse']> {
  const query = assessmentRevisionId
    ? `?assessment_revision_id=${encodeURIComponent(assessmentRevisionId)}`
    : '';
  return apiRequest(
    `/api/v1/recommendations/${encodeURIComponent(recommendationId)}${query}`,
    signal ? { signal } : {},
  );
}
