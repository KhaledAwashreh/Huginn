import { apiRequest } from '../../../../api/client';
import type { operations } from '../../../../api/generated/schema';

export type DeleteServiceOfferingRequest =
  operations['delete_offering_api_v1_offerings__offering_id__delete']['parameters']['path'];
export type DeleteServiceOfferingResponse = void;

export function deleteServiceOffering(id: string): Promise<DeleteServiceOfferingResponse> {
  return apiRequest(`/api/v1/offerings/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
