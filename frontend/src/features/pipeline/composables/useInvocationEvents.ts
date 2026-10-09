import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import type { components } from '../../../api/generated/schema';
import { useSession } from '../../session/composables/useSession';
import { listInvocationEvents } from '../api/listInvocationEvents';

const PAGE_SIZE = 100;
const ACTIVE = new Set(['queued', 'running']);

function visible(): boolean {
  return typeof document === 'undefined' || document.visibilityState === 'visible';
}

export function useInvocationEvents(invocationId: () => string, state: () => string | undefined) {
  const session = useSession();
  const pageVisible = ref(
    typeof document === 'undefined' || document.visibilityState === 'visible',
  );
  const queryClient = useQueryClient();
  const afterSequence = ref(0);
  const entries = ref<components['schemas']['EventEntryResponse'][]>([]);
  const id = computed(invocationId);
  const currentState = computed(state);
  const queryKey = computed(
    () =>
      [
        'admin',
        'pipeline',
        session.context.value?.account_id,
        'events',
        id.value,
        afterSequence.value,
      ] as const,
  );
  const page = useQuery({
    queryKey,
    staleTime: () => (currentState.value && !ACTIVE.has(currentState.value) ? Infinity : 0),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    enabled: computed(
      () => pageVisible.value && session.isAdministrator.value && id.value.length > 0,
    ),
    queryFn: ({ signal }) =>
      listInvocationEvents({
        invocationId: id.value,
        afterSequence: afterSequence.value,
        limit: PAGE_SIZE,
        signal,
      }),
    refetchInterval: (query) => {
      if (!visible() || !ACTIVE.has(currentState.value ?? '') || query.state.data?.has_more)
        return false;
      return query.state.fetchFailureCount
        ? Math.min(1000 * 2 ** query.state.fetchFailureCount, 30_000)
        : 3000;
    },
    retry: (failureCount, error) =>
      !(error instanceof ApiError && [401, 403, 404, 422].includes(error.status)) &&
      failureCount < 5,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
  });

  function onVisibilityChange(): void {
    pageVisible.value = document.visibilityState === 'visible';
    if (document.visibilityState === 'hidden')
      void queryClient.cancelQueries({ queryKey: queryKey.value });
  }
  onMounted(() => document.addEventListener('visibilitychange', onVisibilityChange));
  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisibilityChange);
    void queryClient.cancelQueries({ queryKey: queryKey.value });
  });

  watch(id, () => {
    afterSequence.value = 0;
    entries.value = [];
  });
  watch(page.data, (next) => {
    if (!next) return;
    const bySequence = new Map(entries.value.map((entry) => [entry.sequence, entry]));
    for (const event of next.items) bySequence.set(event.sequence, event);
    entries.value = [...bySequence.values()].sort((left, right) => left.sequence - right.sequence);
    if (!next.has_more && next.next_after_sequence > afterSequence.value)
      afterSequence.value = next.next_after_sequence;
  });

  watch(currentState, (next, previous) => {
    if (ACTIVE.has(previous ?? '') && next && !ACTIVE.has(next)) void page.refetch();
  });

  function loadNext(): void {
    if (!page.data.value?.has_more) return;
    afterSequence.value = page.data.value.next_after_sequence;
  }

  return { page, entries, loadNext };
}
