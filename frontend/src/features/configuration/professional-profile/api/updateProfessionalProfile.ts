import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';

export type UpdateProfessionalProfileRequest =
  components['schemas']['ProfessionalProfileUpdateRequest'];
export type UpdateProfessionalProfileResponse =
  components['schemas']['ProfessionalProfileResponse'];

export const updateProfessionalProfile = (
  request: UpdateProfessionalProfileRequest,
): Promise<UpdateProfessionalProfileResponse> =>
  apiRequest('/api/v1/me/professional-profile', { method: 'PATCH', body: request });
