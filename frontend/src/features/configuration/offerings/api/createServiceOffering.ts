import { apiRequest } from '../../../../api/client';
import type { components, operations } from '../../../../api/generated/schema';

export type CreateServiceOfferingRequest =
  operations['create_offering_api_v1_offerings_post']['requestBody']['content']['application/json'];
export type CreateServiceOfferingResponse = components['schemas']['ServiceOfferingResponse'];

export function createServiceOffering(
  body: CreateServiceOfferingRequest,
): Promise<CreateServiceOfferingResponse> {
  return apiRequest('/api/v1/offerings', { method: 'POST', body });
}
