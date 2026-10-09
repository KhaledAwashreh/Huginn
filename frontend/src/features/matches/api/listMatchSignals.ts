import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type MatchSignalsPage = components['schemas']['PageResponse_CurrentCompanySignalResponse_'];

export interface ListMatchSignalsOptions {
  matchId: string;
  limit: number;
  offset: number;
  signal?: AbortSignal;
}

export function listMatchSignals({ matchId, limit, offset, signal }: ListMatchSignalsOptions) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiRequest<MatchSignalsPage>(
    `/api/v1/matches/${encodeURIComponent(matchId)}/signals?${query.toString()}`,
    signal ? { signal } : {},
  );
}
