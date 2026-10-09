import { apiRequest } from '../../../../api/client';
import type { components, operations } from '../../../../api/generated/schema';

export type ListIdealClientProfilesRequest =
  operations['list_ideal_client_profiles_api_v1_ideal_client_profiles_get']['parameters']['query'];
export type ListIdealClientProfilesResponse =
  components['schemas']['PageResponse_IdealClientProfileResponse_'];

export function listIdealClientProfiles(
  offset = 0,
  limit = 100,
  signal?: AbortSignal,
): Promise<ListIdealClientProfilesResponse> {
  const safeOffset = Math.max(0, Math.floor(offset));
  const safeLimit = Math.min(100, Math.max(1, Math.floor(limit)));
  const query = new URLSearchParams({ limit: String(safeLimit), offset: String(safeOffset) });
  return apiRequest(`/api/v1/ideal-client-profiles?${query}`, signal ? { signal } : {});
}
