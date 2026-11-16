import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export interface ListProspectsOptions {
  stage: components['schemas']['ProspectResponse']['stage'] | 'all';
  search: string;
  offset: number;
  limit: number;
}

export function listProspects(
  { stage, search, offset, limit }: ListProspectsOptions,
  signal?: AbortSignal,
): Promise<components['schemas']['PageResponse_ProspectResponse_']> {
  const query = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (stage !== 'all') query.set('stage', stage);
  if (search.trim()) query.set('search', search.trim());
  return apiRequest(`/api/v1/prospects?${query.toString()}`, signal ? { signal } : {});
}
