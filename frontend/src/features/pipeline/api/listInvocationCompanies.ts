import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type InvocationCompaniesResponse = components['schemas']['InvocationCompaniesResponse'];

export interface ListInvocationCompaniesOptions {
  invocationId: string;
  limit: number;
  offset: number;
  signal?: AbortSignal;
}

export function listInvocationCompanies({
  invocationId,
  limit,
  offset,
  signal,
}: ListInvocationCompaniesOptions) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiRequest<InvocationCompaniesResponse>(
    `/api/v1/admin/pipeline/invocations/${encodeURIComponent(invocationId)}/companies?${query.toString()}`,
    signal ? { signal } : {},
  );
}
