import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type InvocationDetailResponse = components['schemas']['InvocationDetailResponse'];

export const getInvocation = (invocationId: string, signal?: AbortSignal) =>
  apiRequest<InvocationDetailResponse>(
    `/api/v1/admin/pipeline/invocations/${encodeURIComponent(invocationId)}`,
    signal ? { signal } : {},
  );
