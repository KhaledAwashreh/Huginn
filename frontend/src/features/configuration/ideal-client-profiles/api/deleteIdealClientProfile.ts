import { apiRequest } from '../../../../api/client';
import type { operations } from '../../../../api/generated/schema';

export type DeleteIdealClientProfileRequest =
  operations['delete_ideal_client_profile_api_v1_ideal_client_profiles__profile_id__delete']['parameters']['path'];
export type DeleteIdealClientProfileResponse = void;

export function deleteIdealClientProfile(id: string): Promise<DeleteIdealClientProfileResponse> {
  return apiRequest(`/api/v1/ideal-client-profiles/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}
