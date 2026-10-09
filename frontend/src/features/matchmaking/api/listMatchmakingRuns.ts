import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type MatchmakingRunsPage = components['schemas']['PageResponse_RunSummaryResponse_'];
export type MatchmakingRunState = components['schemas']['RunState'];

export interface ListMatchmakingRunsOptions {
  limit: number;
  offset: number;
  state?: MatchmakingRunState;
  signal?: AbortSignal;
}

export function listMatchmakingRuns({ limit, offset, state, signal }: ListMatchmakingRunsOptions) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (state) query.set('state', state);
  return apiRequest<MatchmakingRunsPage>(
    `/api/v1/admin/matchmaking/runs?${query.toString()}`,
    signal ? { signal } : {},
  );
}
