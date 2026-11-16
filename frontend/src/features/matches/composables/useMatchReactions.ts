import { computed, ref } from 'vue';
import { useSession } from '../../session/composables/useSession';
import type { FeedbackReason } from '../../recommendations/models/recommendationFeedback';

export type MatchReaction = {
  matchId: string;
  companyName: string;
  kind: 'up' | 'down';
  reason?: FeedbackReason;
  note?: string;
};

type ReactableMatch = { id: string; company: { name: string } };

// UI prototype: no API stores reactions on Matches yet, so they last only until the page reloads.
const reactions = ref(new Map<string, MatchReaction>());

export function useMatchReactions() {
  const session = useSession();
  const owner = computed(() => session.context.value?.user_id ?? '');
  const key = (matchId: string) => `${owner.value}:${matchId}`;

  function reactionFor(matchId: string): MatchReaction | undefined {
    return reactions.value.get(key(matchId));
  }
  function markGood(match: ReactableMatch): void {
    reactions.value.set(key(match.id), {
      matchId: match.id,
      companyName: match.company.name,
      kind: 'up',
    });
  }
  function markNotAFit(match: ReactableMatch, reason: FeedbackReason, note: string): void {
    reactions.value.set(key(match.id), {
      matchId: match.id,
      companyName: match.company.name,
      kind: 'down',
      reason,
      ...(note.trim() ? { note: note.trim() } : {}),
    });
  }
  function clearReaction(matchId: string): void {
    reactions.value.delete(key(matchId));
  }
  const allReactions = computed(() =>
    [...reactions.value.entries()]
      .filter(([entryKey]) => entryKey.startsWith(`${owner.value}:`))
      .map(([, reaction]) => reaction),
  );

  return { reactionFor, markGood, markNotAFit, clearReaction, allReactions };
}
