import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type InvocationHistoryResponse = components['schemas']['InvocationHistoryResponse'];
export type InvocationStateFilter = 'queued' | 'running' | 'succeeded' | 'failed' | 'interrupted';

export interface ListInvocationsOptions {
  limit: number;
  offset: number;
  state?: InvocationStateFilter;
  signal?: AbortSignal;
}

export function listInvocations({ limit, offset, state, signal }: ListInvocationsOptions) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (state) query.set('state', state);
  return apiRequest<InvocationHistoryResponse>(
    `/api/v1/admin/pipeline/invocations?${query.toString()}`,
    signal ? { signal } : {},
  );
}
