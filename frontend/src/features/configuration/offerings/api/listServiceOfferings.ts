import { apiRequest } from '../../../../api/client';
import type { components, operations } from '../../../../api/generated/schema';

export type ListServiceOfferingsRequest =
  operations['list_offerings_api_v1_offerings_get']['parameters']['query'];
export type ListServiceOfferingsResponse =
  components['schemas']['PageResponse_ServiceOfferingResponse_'];

export function listServiceOfferings(
  offset = 0,
  limit = 100,
  signal?: AbortSignal,
): Promise<ListServiceOfferingsResponse> {
  const safeOffset = Math.max(0, Math.floor(offset));
  const safeLimit = Math.min(100, Math.max(1, Math.floor(limit)));
  const query = new URLSearchParams({ limit: String(safeLimit), offset: String(safeOffset) });
  return apiRequest(`/api/v1/offerings?${query}`, signal ? { signal } : {});
}
