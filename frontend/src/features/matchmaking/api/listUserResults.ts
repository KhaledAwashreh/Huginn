import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type UserResultsPage = components['schemas']['PageResponse_UserResultResponse_'];
export type UserResult = components['schemas']['UserResultResponse'];
export type MatchmakingTargetState = components['schemas']['TargetState'];

export interface ListUserResultsOptions {
  runId: string;
  limit: number;
  offset: number;
  state?: MatchmakingTargetState;
  signal?: AbortSignal;
}

export function listUserResults({ runId, limit, offset, state, signal }: ListUserResultsOptions) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (state) query.set('state', state);
  return apiRequest<UserResultsPage>(
    `/api/v1/admin/matchmaking/runs/${encodeURIComponent(runId)}/users?${query.toString()}`,
    signal ? { signal } : {},
  );
}
