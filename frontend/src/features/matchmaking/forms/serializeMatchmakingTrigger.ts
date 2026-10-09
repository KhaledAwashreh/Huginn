import type { components } from '../../../api/generated/schema';
import type { MatchmakingTriggerDraft } from './matchmakingTriggerDraft';

export type TriggerMatchmakingBody = components['schemas']['TriggerRunBody'];

function toUtcIso(value: string): string {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) throw new Error('Choose valid start and end dates.');
  return date.toISOString();
}

export function serializeMatchmakingTrigger(
  draft: MatchmakingTriggerDraft,
  requestId: string,
): TriggerMatchmakingBody {
  const cutoff = toUtcIso(draft.cutoffLocal);
  const asOf = toUtcIso(draft.asOfLocal);
  if (Date.parse(cutoff) > Date.parse(asOf))
    throw new Error('The signal window start must be before its end.');
  if (Date.parse(asOf) > Date.now())
    throw new Error('The signal window end cannot be in the future.');
  let target: TriggerMatchmakingBody['target'];
  if (draft.targetKind === 'all_eligible') target = { kind: 'all_eligible' };
  else {
    const selectedUser = draft.selectedUser;
    if (!selectedUser) throw new Error('Choose one user before starting a single-user run.');
    target = { kind: 'user', user_id: selectedUser.id };
  }
  return {
    request_id: requestId,
    cutoff,
    as_of: asOf,
    target,
  };
}
