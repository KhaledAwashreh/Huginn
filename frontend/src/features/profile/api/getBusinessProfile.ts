import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type BusinessProfileResponse = components['schemas']['BusinessProfileResponse'];

export const getBusinessProfile = (signal?: AbortSignal): Promise<BusinessProfileResponse> =>
  apiRequest('/api/v1/me/business', signal ? { signal } : {});
