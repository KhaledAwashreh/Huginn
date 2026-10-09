import { apiRequest } from '../../../../api/client';
import type { components, operations } from '../../../../api/generated/schema';

export type GetServiceOfferingRequest =
  operations['get_offering_api_v1_offerings__offering_id__get']['parameters']['path'];
export type GetServiceOfferingResponse = components['schemas']['ServiceOfferingResponse'];

export function getServiceOffering(
  id: string,
  signal?: AbortSignal,
): Promise<GetServiceOfferingResponse> {
  return apiRequest(`/api/v1/offerings/${encodeURIComponent(id)}`, signal ? { signal } : {});
}
