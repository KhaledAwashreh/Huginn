import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type BusinessProfileUpdateRequest = components['schemas']['BusinessProfileUpdateRequest'];
export type BusinessProfileUpdateResponse = components['schemas']['BusinessProfileResponse'];

export const updateBusinessProfile = (
  request: BusinessProfileUpdateRequest,
): Promise<BusinessProfileUpdateResponse> =>
  apiRequest('/api/v1/me/business', { method: 'PATCH', body: request });
