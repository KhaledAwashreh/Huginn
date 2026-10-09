import type { LocationQuery, LocationQueryRaw } from 'vue-router';
import type { InvocationStateFilter } from '../api/listInvocations';

export type PipelineStageTab = 'bronze' | 'silver' | 'gold';

export interface PipelineQuery {
  stage: PipelineStageTab;
  state?: InvocationStateFilter;
  offset: number;
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const STATES = new Set<InvocationStateFilter>([
  'queued',
  'running',
  'succeeded',
  'failed',
  'interrupted',
]);
const STAGES = new Set<PipelineStageTab>(['bronze', 'silver', 'gold']);

function first(query: LocationQuery, key: string): string | undefined {
  const value = query[key];
  return typeof value === 'string' ? value : undefined;
}

export function validateInvocationId(value: unknown): value is string {
  return typeof value === 'string' && UUID_PATTERN.test(value);
}

export function validatePipelineQuery(query: LocationQuery): PipelineQuery {
  const rawStage = first(query, 'stage');
  const rawState = first(query, 'state');
  const rawOffset = Number(first(query, 'offset') ?? '0');
  return {
    stage:
      rawStage && STAGES.has(rawStage as PipelineStageTab)
        ? (rawStage as PipelineStageTab)
        : 'bronze',
    ...(rawState && STATES.has(rawState as InvocationStateFilter)
      ? { state: rawState as InvocationStateFilter }
      : {}),
    offset: Number.isSafeInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0,
  };
}

export function pipelineQueryLocation(query: PipelineQuery): LocationQueryRaw {
  return {
    ...(query.stage === 'bronze' ? {} : { stage: query.stage }),
    ...(query.state ? { state: query.state } : {}),
    ...(query.offset > 0 ? { offset: String(query.offset) } : {}),
  };
}
