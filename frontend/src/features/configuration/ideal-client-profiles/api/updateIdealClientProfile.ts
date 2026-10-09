import { apiRequest } from '../../../../api/client';
import type { components, operations } from '../../../../api/generated/schema';

export type UpdateIdealClientProfileRequest =
  operations['update_ideal_client_profile_api_v1_ideal_client_profiles__profile_id__patch']['requestBody']['content']['application/json'];
export type UpdateIdealClientProfileResponse = components['schemas']['IdealClientProfileResponse'];

export function updateIdealClientProfile(
  id: string,
  body: UpdateIdealClientProfileRequest,
): Promise<UpdateIdealClientProfileResponse> {
  return apiRequest(`/api/v1/ideal-client-profiles/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body,
  });
}
