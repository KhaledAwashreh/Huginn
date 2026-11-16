import { expect, it } from 'vitest';
import type { components } from '../../../src/api/generated/schema';
import {
  activityLabel,
  activitySummary,
  canCorrectActivityTime,
  orderProspectActivities,
} from '../../../src/features/prospects/models/prospectActivityTimeline';

type Activity = components['schemas']['ProspectActivityResponse'];

function activity(id: string, recordedAt: string, overrides: Partial<Activity> = {}): Activity {
  return {
    id,
    business_id: 'business-1',
    prospect_id: 'prospect-1',
    actor_user_id: 'user-1',
    kind: 'stage_changed',
    occurred_at: '2026-11-01T10:00:00Z',
    effective_occurred_at: '2026-11-01T10:00:00Z',
    recorded_at: recordedAt,
    payload: { reason: 'Verified progress' },
    correction_of_id: null,
    correction_head_id: null,
    correction_sequence: 0,
    ...overrides,
  };
}

it('orders immutable activity by recorded time and uses sequence for equal-time corrections', () => {
  const entries = [
    activity('correction-2', '2026-11-03T10:00:00Z', {
      kind: 'correction',
      correction_of_id: 'activity-1',
      correction_sequence: 0,
      payload: { correction_sequence: 2 },
    }),
    activity('activity-1', '2026-11-01T10:00:00Z'),
    activity('correction-1', '2026-11-03T10:00:00Z', {
      kind: 'correction',
      correction_of_id: 'activity-1',
      correction_sequence: 0,
      payload: { correction_sequence: 1 },
    }),
  ];

  expect(orderProspectActivities(entries).map((entry) => entry.id)).toEqual([
    'activity-1',
    'correction-1',
    'correction-2',
  ]);
  expect(orderProspectActivities(entries)[0]?.effective_occurred_at).toBe('2026-11-01T10:00:00Z');
});

it('only allows correction of original activity and gives unknown kinds a neutral label', () => {
  const original = activity('original', '2026-11-01T10:00:00Z');
  const correction = activity('correction', '2026-11-02T10:00:00Z', {
    kind: 'correction',
    correction_of_id: 'original',
  });

  expect(canCorrectActivityTime(original)).toBe(true);
  expect(canCorrectActivityTime(correction)).toBe(false);
  expect(activityLabel('unrecognized_future_kind')).toBe('Other recorded activity');
});

it('renders actual stage, notes, follow-up and correction activity payloads', () => {
  expect(
    activitySummary(
      activity('stage', '2026-11-01T10:00:00Z', {
        payload: {
          prior_stage: 'proposal_sent',
          new_stage: 'in_conversation',
          reason: 'They requested more time.',
        },
      }),
    ),
  ).toContain('They requested more time.');
  expect(
    activitySummary(
      activity('notes', '2026-11-01T10:00:00Z', {
        kind: 'note_added',
        payload: { prior: 'Old memo', replacement: 'Updated memo' },
      }),
    ),
  ).toContain('Old memo');
  expect(
    activitySummary(
      activity('follow-up', '2026-11-01T10:00:00Z', {
        kind: 'follow_up_set',
        payload: { prior: null, replacement: '2026-11-20T09:00:00Z' },
      }),
    ),
  ).toContain('2026-11-20');
  expect(
    activitySummary(
      activity('correction', '2026-11-01T10:00:00Z', {
        kind: 'correction',
        correction_sequence: 0,
        payload: {
          prior: '2026-11-01T10:00:00Z',
          replacement: '2026-10-31T10:00:00Z',
          correction_sequence: 3,
        },
      }),
    ),
  ).toContain('Correction 3:');
});
