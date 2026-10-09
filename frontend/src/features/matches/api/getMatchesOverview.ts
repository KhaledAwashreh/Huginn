import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export type MatchesOverview = components['schemas']['MatchesOverviewResponse'];

export function getMatchesOverview(signal?: AbortSignal) {
  return apiRequest<MatchesOverview>('/api/v1/matches/overview', signal ? { signal } : {});
}
