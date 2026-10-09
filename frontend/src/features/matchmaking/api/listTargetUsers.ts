import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type TargetUserPageResponse = components['schemas']['TargetUserPageResponse'];

export interface ListTargetUsersOptions {
  search: string;
  offset: number;
  limit: number;
  signal?: AbortSignal;
}

export function listTargetUsers({ search, offset, limit, signal }: ListTargetUsersOptions) {
  const query = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (search) query.set('search', search);
  return apiRequest<TargetUserPageResponse>(
    `/api/v1/admin/matchmaking/users?${query.toString()}`,
    signal ? { signal } : {},
  );
}
