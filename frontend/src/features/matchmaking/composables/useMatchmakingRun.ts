import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { useSession } from '../../session/composables/useSession';
import { getMatchmakingRun } from '../api/getMatchmakingRun';
import { listUserResults, type MatchmakingTargetState } from '../api/listUserResults';

const PAGE_SIZE = 20;
const ACTIVE = new Set(['queued', 'running']);

function visible(): boolean {
  return typeof document === 'undefined' || document.visibilityState === 'visible';
}

function retry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && [401, 403, 404, 422].includes(error.status)) return false;
  return failureCount < 5;
}

export function useMatchmakingRun(runId: () => string, offset: () => number) {
  const session = useSession();
  const queryClient = useQueryClient();
  const id = computed(runId);
  const currentOffset = computed(offset);
  const state = ref<MatchmakingTargetState | undefined>();
  const detailKey = computed(
    () => ['admin', 'matchmaking', session.context.value?.account_id, 'run', id.value] as const,
  );
  const run = useQuery({
    queryKey: detailKey,
    enabled: computed(() => session.isAdministrator.value && id.value.length > 0),
    queryFn: ({ signal }) => getMatchmakingRun(id.value, signal),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchIntervalInBackground: false,
    refetchInterval: (query) => {
      if (!visible() || !ACTIVE.has(query.state.data?.state ?? '')) return false;
      return query.state.fetchFailureCount
        ? Math.min(1000 * 2 ** query.state.fetchFailureCount, 30_000)
        : 3000;
    },
    retry,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
  });
  const resultsKey = computed(
    () =>
      [
        'admin',
        'matchmaking',
        session.context.value?.account_id,
        'run-users',
        id.value,
        state.value ?? null,
        currentOffset.value,
      ] as const,
  );
  const results = useQuery({
    queryKey: resultsKey,
    enabled: computed(() => session.isAdministrator.value && id.value.length > 0),
    queryFn: ({ signal }) =>
      listUserResults({
        runId: id.value,
        limit: PAGE_SIZE,
        offset: currentOffset.value,
        ...(state.value ? { state: state.value } : {}),
        signal,
      }),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchIntervalInBackground: false,
    refetchInterval: (query) => {
      if (!visible() || !ACTIVE.has(run.data.value?.state ?? '')) return false;
      return query.state.fetchFailureCount
        ? Math.min(1000 * 2 ** query.state.fetchFailureCount, 30_000)
        : 3000;
    },
    retry,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
  });

  function onVisibilityChange(): void {
    if (document.visibilityState === 'hidden') {
      void queryClient.cancelQueries({ queryKey: detailKey.value });
      void queryClient.cancelQueries({ queryKey: resultsKey.value });
    } else if (session.isAdministrator.value && id.value) {
      if (!run.data.value || ACTIVE.has(run.data.value.state)) {
        void run.refetch();
        void results.refetch();
      }
    }
  }
  onMounted(() => document.addEventListener('visibilitychange', onVisibilityChange));
  onBeforeUnmount(() => document.removeEventListener('visibilitychange', onVisibilityChange));

  watch(
    () => run.data.value?.state,
    (next, previous) => {
      if (previous && ACTIVE.has(previous) && next && !ACTIVE.has(next)) void results.refetch();
    },
  );
  watch(id, () => {
    state.value = undefined;
  });

  return { run, results, state, offset: currentOffset, pageSize: PAGE_SIZE };
}
