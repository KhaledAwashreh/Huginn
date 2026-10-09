import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { listMatchSignals } from '../api/listMatchSignals';

const SIGNAL_PAGE_SIZE = 50;

export function useMatchSignals(matchId: MaybeRefOrGetter<string | undefined>) {
  const session = useSession();
  const offset = ref(0);
  watch(
    () => toValue(matchId),
    () => {
      offset.value = 0;
    },
  );
  const queryKey = computed(
    () =>
      [
        'matches',
        session.context.value?.account_id,
        session.context.value?.user_id,
        'signals',
        toValue(matchId),
        offset.value,
      ] as const,
  );
  const signals = useQuery({
    queryKey,
    enabled: computed(() => Boolean(session.context.value && toValue(matchId))),
    queryFn: ({ signal }) =>
      listMatchSignals({
        matchId: toValue(matchId) ?? '',
        limit: SIGNAL_PAGE_SIZE,
        offset: offset.value,
        signal,
      }),
    placeholderData: (previousData, previousQuery) => {
      const previousKey = previousQuery?.queryKey;
      return previousKey?.[0] === 'matches' &&
        previousKey[1] === queryKey.value[1] &&
        previousKey[2] === queryKey.value[2] &&
        previousKey[4] === queryKey.value[4]
        ? previousData
        : undefined;
    },
  });
  return {
    signals,
    offset,
    pageSize: SIGNAL_PAGE_SIZE,
    previousPage: () => (offset.value = Math.max(0, offset.value - SIGNAL_PAGE_SIZE)),
    nextPage: () => {
      if (signals.data.value?.has_more) offset.value += SIGNAL_PAGE_SIZE;
    },
  };
}
