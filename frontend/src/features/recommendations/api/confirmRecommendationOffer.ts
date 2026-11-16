import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function confirmRecommendationOffer(
  offerCycleId: string,
  request: components['schemas']['ConfirmRecommendationOfferRequest'],
): Promise<components['schemas']['ConfirmedRecommendationOfferResponse']> {
  return apiRequest(
    `/api/v1/recommendations/offer-preparations/${encodeURIComponent(offerCycleId)}/confirm`,
    {
      method: 'POST',
      body: request,
    },
  );
}
