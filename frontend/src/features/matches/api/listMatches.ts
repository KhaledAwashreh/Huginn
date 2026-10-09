import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type MatchPage = components['schemas']['PageResponse_UserMatchResponse_'];
export type UserMatch = components['schemas']['UserMatchResponse'];
export type MatchStatusFilter = 'new' | 'contacted' | 'responded' | 'dismissed' | 'converted';

export interface ListMatchesOptions {
  limit: number;
  offset: number;
  status?: MatchStatusFilter;
  signal?: AbortSignal;
}

export function listMatches({ limit, offset, status, signal }: ListMatchesOptions) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (status) query.set('status', status);
  return apiRequest<MatchPage>(`/api/v1/matches?${query.toString()}`, signal ? { signal } : {});
}
