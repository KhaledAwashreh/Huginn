import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';

export type GetProfessionalProfileResponse = components['schemas']['ProfessionalProfileResponse'];

export const getProfessionalProfile = (
  signal?: AbortSignal,
): Promise<GetProfessionalProfileResponse> =>
  apiRequest('/api/v1/me/professional-profile', signal ? { signal } : {});
