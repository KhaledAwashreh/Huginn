import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function getBusinessRecommendationPreferences(
  signal?: AbortSignal,
): Promise<components['schemas']['BusinessRecommendationPreferencesResponse']> {
  return apiRequest('/api/v1/me/business/recommendation-preferences', signal ? { signal } : {});
}
