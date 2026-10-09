import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type InvocationEventsResponse = components['schemas']['EventPageResponse'];

export interface ListInvocationEventsOptions {
  invocationId: string;
  afterSequence: number;
  limit: number;
  signal?: AbortSignal;
}

export function listInvocationEvents({
  invocationId,
  afterSequence,
  limit,
  signal,
}: ListInvocationEventsOptions) {
  const query = new URLSearchParams({
    after_sequence: String(afterSequence),
    limit: String(limit),
  });
  return apiRequest<InvocationEventsResponse>(
    `/api/v1/admin/pipeline/invocations/${encodeURIComponent(invocationId)}/events?${query.toString()}`,
    signal ? { signal } : {},
  );
}
