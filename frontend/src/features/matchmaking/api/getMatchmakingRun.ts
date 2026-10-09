import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type MatchmakingRunDetail = components['schemas']['RunDetailResponse'];

export const getMatchmakingRun = (runId: string, signal?: AbortSignal) =>
  apiRequest<MatchmakingRunDetail>(
    `/api/v1/admin/matchmaking/runs/${encodeURIComponent(runId)}`,
    signal ? { signal } : {},
  );
