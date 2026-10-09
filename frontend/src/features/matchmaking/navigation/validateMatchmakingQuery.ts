import type { LocationQuery } from 'vue-router';
import type { MatchmakingRunState } from '../api/listMatchmakingRuns';

export interface MatchmakingQuery {
  offset: number;
  state?: MatchmakingRunState;
}

const RUN_STATES = new Set<MatchmakingRunState>([
  'queued',
  'running',
  'succeeded',
  'completed_with_errors',
  'interrupted',
]);
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function queryValue(query: LocationQuery, key: string): string | undefined {
  return typeof query[key] === 'string' ? query[key] : undefined;
}

export function validateMatchmakingRunId(value: unknown): value is string {
  return typeof value === 'string' && UUID_PATTERN.test(value);
}

export function validateMatchmakingQuery(query: LocationQuery): MatchmakingQuery {
  const rawState = queryValue(query, 'state');
  const rawOffset = Number(queryValue(query, 'offset') ?? '0');
  return {
    ...(rawState && RUN_STATES.has(rawState as MatchmakingRunState)
      ? { state: rawState as MatchmakingRunState }
      : {}),
    offset: Number.isSafeInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0,
  };
}
