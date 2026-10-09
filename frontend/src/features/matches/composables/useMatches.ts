import { computed, ref, type Ref } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { listMatches, type MatchStatusFilter } from '../api/listMatches';

export const MATCH_PAGE_SIZE = 50;

export function matchesQueryKey(
  accountId: string | undefined,
  userId: string | undefined,
  status: MatchStatusFilter | undefined,
  offset: number,
) {
  return ['matches', accountId, userId, 'list', status ?? null, offset] as const;
}

export function applyMatchStatus(
  currentStatus: Ref<MatchStatusFilter | undefined>,
  currentOffset: Ref<number>,
  nextStatus: MatchStatusFilter | undefined,
): void {
  currentStatus.value = nextStatus;
  currentOffset.value = 0;
}

export function useMatches() {
  const session = useSession();
  const status = ref<MatchStatusFilter | undefined>();
  const offset = ref(0);
  const queryKey = computed(() =>
    matchesQueryKey(
      session.context.value?.account_id,
      session.context.value?.user_id,
      status.value,
      offset.value,
    ),
  );
  const matches = useQuery({
    queryKey,
    enabled: computed(() => Boolean(session.context.value)),
    queryFn: ({ signal }) =>
      listMatches({
        limit: MATCH_PAGE_SIZE,
        offset: offset.value,
        ...(status.value ? { status: status.value } : {}),
        signal,
      }),
    placeholderData: (previousData, previousQuery) => {
      const previousKey = previousQuery?.queryKey;
      return previousKey?.[0] === 'matches' &&
        previousKey[1] === queryKey.value[1] &&
        previousKey[2] === queryKey.value[2]
        ? previousData
        : undefined;
    },
  });

  function setStatus(next: MatchStatusFilter | undefined): void {
    applyMatchStatus(status, offset, next);
  }

  function setOffset(next: number): void {
    offset.value = Math.max(0, next);
  }

  function nextPage(): void {
    if (matches.data.value?.has_more) offset.value += MATCH_PAGE_SIZE;
  }

  function previousPage(): void {
    offset.value = Math.max(0, offset.value - MATCH_PAGE_SIZE);
  }

  return {
    matches,
    status,
    offset,
    pageSize: MATCH_PAGE_SIZE,
    setStatus,
    setOffset,
    nextPage,
    previousPage,
  };
}
