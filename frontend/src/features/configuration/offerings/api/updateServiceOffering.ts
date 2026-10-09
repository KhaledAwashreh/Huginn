import { apiRequest } from '../../../../api/client';
import type { components, operations } from '../../../../api/generated/schema';

export type UpdateServiceOfferingRequest =
  operations['update_offering_api_v1_offerings__offering_id__patch']['requestBody']['content']['application/json'];
export type UpdateServiceOfferingResponse = components['schemas']['ServiceOfferingResponse'];

export function updateServiceOffering(
  id: string,
  body: UpdateServiceOfferingRequest,
): Promise<UpdateServiceOfferingResponse> {
  return apiRequest(`/api/v1/offerings/${encodeURIComponent(id)}`, { method: 'PATCH', body });
}
