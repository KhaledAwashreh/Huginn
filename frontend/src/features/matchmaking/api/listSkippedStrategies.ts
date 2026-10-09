import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type SkippedStrategiesPage =
  components['schemas']['PageResponse_SkippedStrategyResultResponse_'];

export interface ListSkippedStrategiesOptions {
  runId: string;
  userId: string;
  limit: number;
  offset: number;
  signal?: AbortSignal;
}

export function listSkippedStrategies({
  runId,
  userId,
  limit,
  offset,
  signal,
}: ListSkippedStrategiesOptions) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiRequest<SkippedStrategiesPage>(
    `/api/v1/admin/matchmaking/runs/${encodeURIComponent(runId)}/users/${encodeURIComponent(userId)}/skipped-strategies?${query.toString()}`,
    signal ? { signal } : {},
  );
}
