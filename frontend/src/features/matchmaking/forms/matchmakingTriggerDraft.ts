import type { components } from '../../../api/generated/schema';

export type TargetUser = components['schemas']['TargetUserResponse'];
export type SignalWindowPreset = '7' | '30' | '90' | 'custom';

export interface MatchmakingTriggerDraft {
  targetKind: 'user' | 'all_eligible';
  selectedUser: TargetUser | null;
  windowPreset: SignalWindowPreset;
  cutoffLocal: string;
  asOfLocal: string;
}

function asLocalDateTime(date: Date): string {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

export function createMatchmakingTriggerDraft(now = new Date()): MatchmakingTriggerDraft {
  const asOf = new Date(now);
  const cutoff = new Date(asOf);
  cutoff.setDate(cutoff.getDate() - 30);
  return {
    targetKind: 'user',
    selectedUser: null,
    windowPreset: '30',
    cutoffLocal: asLocalDateTime(cutoff),
    asOfLocal: asLocalDateTime(asOf),
  };
}
