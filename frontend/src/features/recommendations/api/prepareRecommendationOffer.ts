import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function prepareRecommendationOffer(
  recommendationId: string,
  request: components['schemas']['PrepareRecommendationOfferRequest'],
): Promise<components['schemas']['PreparedRecommendationOfferResponse']> {
  return apiRequest(
    `/api/v1/recommendations/${encodeURIComponent(recommendationId)}/offer-preparations`,
    {
      method: 'POST',
      body: request,
    },
  );
}
