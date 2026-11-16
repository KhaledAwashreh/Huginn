import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export interface ListSuppressionsOptions {
  search: string;
  offset: number;
  limit: number;
}

export function listSuppressions(
  { search, offset, limit }: ListSuppressionsOptions,
  signal?: AbortSignal,
): Promise<components['schemas']['PageResponse_SuppressionResponse_']> {
  const query = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (search) query.set('search', search);
  return apiRequest(`/api/v1/suppressions?${query.toString()}`, signal ? { signal } : {});
}
