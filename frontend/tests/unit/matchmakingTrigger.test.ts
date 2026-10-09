import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createMatchmakingTriggerDraft } from '@/features/matchmaking/forms/matchmakingTriggerDraft';
import { serializeMatchmakingTrigger } from '@/features/matchmaking/forms/serializeMatchmakingTrigger';
import { validateMatchmakingRunId } from '@/features/matchmaking/navigation/validateMatchmakingQuery';

const user = {
  id: '1f891e25-047d-4c76-bf6d-701c28e47b31',
  username: 'northstar',
  first_name: 'North',
  last_name: 'Star',
  has_active_strategies: true,
};

describe('matchmaking trigger scope and window', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-09T12:00:00.000Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('starts with a single-user draft and serializes a stable offset-aware payload', () => {
    const draft = createMatchmakingTriggerDraft(new Date('2026-10-09T12:00:00.000Z'));
    expect(draft.targetKind).toBe('user');
    expect(draft.windowPreset).toBe('30');
    const body = serializeMatchmakingTrigger({ ...draft, selectedUser: user }, 'request-1');
    expect(body).toEqual({
      request_id: 'request-1',
      cutoff: '2026-09-09T12:00:00.000Z',
      as_of: '2026-10-09T12:00:00.000Z',
      target: { kind: 'user', user_id: user.id },
    });
  });

  it('serializes all-eligible only when deliberately selected and rejects invalid windows', () => {
    const draft = createMatchmakingTriggerDraft(new Date('2026-10-09T12:00:00.000Z'));
    expect(
      serializeMatchmakingTrigger({ ...draft, targetKind: 'all_eligible' }, 'request-2').target,
    ).toEqual({ kind: 'all_eligible' });
    expect(() =>
      serializeMatchmakingTrigger({ ...draft, cutoffLocal: '', selectedUser: user }, 'request-3'),
    ).toThrow('Choose valid start and end dates.');
    expect(() =>
      serializeMatchmakingTrigger(
        { ...draft, cutoffLocal: '2026-10-10T12:00', selectedUser: user },
        'request-4',
      ),
    ).toThrow('The signal window start must be before its end.');
  });

  it('accepts UUID-shaped run IDs without imposing a version/variant policy', () => {
    expect(validateMatchmakingRunId('00000000-0000-0000-0000-00000000238d')).toBe(true);
    expect(validateMatchmakingRunId('not-a-run-id')).toBe(false);
  });
});
