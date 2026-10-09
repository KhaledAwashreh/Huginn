import { apiRequest } from '../../../../api/client';
import type { components, operations } from '../../../../api/generated/schema';

export type GetIdealClientProfileRequest =
  operations['get_ideal_client_profile_api_v1_ideal_client_profiles__profile_id__get']['parameters']['path'];
export type GetIdealClientProfileResponse = components['schemas']['IdealClientProfileResponse'];

export function getIdealClientProfile(
  id: string,
  signal?: AbortSignal,
): Promise<GetIdealClientProfileResponse> {
  return apiRequest(
    `/api/v1/ideal-client-profiles/${encodeURIComponent(id)}`,
    signal ? { signal } : {},
  );
}
