import { apiRequest } from '../../../../api/client';
import type { components, operations } from '../../../../api/generated/schema';

export type CreateIdealClientProfileRequest =
  operations['create_ideal_client_profile_api_v1_ideal_client_profiles_post']['requestBody']['content']['application/json'];
export type CreateIdealClientProfileResponse = components['schemas']['IdealClientProfileResponse'];

export function createIdealClientProfile(
  body: CreateIdealClientProfileRequest,
): Promise<CreateIdealClientProfileResponse> {
  return apiRequest('/api/v1/ideal-client-profiles', { method: 'POST', body });
}
