import type { components } from '../../../api/generated/schema';

export type AssessmentRevision = components['schemas']['AssessmentRevisionResponse'];
export type StrategyAssessment = AssessmentRevision['strategy_assessments'][number];
export type JsonRecord = Record<string, unknown>;

export function record(value: unknown): JsonRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

export function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

export function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function strategyName(item: StrategyAssessment): string {
  return text(record(item.strategy_snapshot).name) ?? 'Discovery strategy';
}

export function retainedEvidence(
  assessment: AssessmentRevision,
  item: StrategyAssessment,
): JsonRecord[] {
  const lineage = new Map(
    assessment.evidence_snapshots
      .map(record)
      .map((snapshot) => [text(snapshot.observation_id), snapshot] as const)
      .filter((entry): entry is readonly [string, JsonRecord] => entry[0] !== null),
  );
  return list(record(item.assessment_snapshot).evidence).map((value) => {
    const entry = record(value);
    const snapshot = lineage.get(text(entry.observation_id) ?? '');
    return snapshot ? { ...snapshot, quote: text(entry.quote) ?? snapshot.quote } : entry;
  });
}
