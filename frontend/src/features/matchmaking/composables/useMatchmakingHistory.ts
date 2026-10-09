import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { useSession } from '../../session/composables/useSession';
import { listMatchmakingRuns, type MatchmakingRunState } from '../api/listMatchmakingRuns';

const PAGE_SIZE = 20;

function visible(): boolean {
  return typeof document === 'undefined' || document.visibilityState === 'visible';
}

export function useMatchmakingHistory() {
  const session = useSession();
  const queryClient = useQueryClient();
  const state = ref<MatchmakingRunState | undefined>();
  const offset = ref(0);
  function setState(next: MatchmakingRunState | undefined): void {
    state.value = next;
    offset.value = 0;
  }
  const queryKey = computed(
    () =>
      [
        'admin',
        'matchmaking',
        session.context.value?.account_id,
        'history',
        state.value ?? null,
        offset.value,
      ] as const,
  );
  const history = useQuery({
    queryKey,
    enabled: computed(() => session.isAdministrator.value),
    queryFn: ({ signal }) =>
      listMatchmakingRuns({
        limit: PAGE_SIZE,
        offset: offset.value,
        ...(state.value ? { state: state.value } : {}),
        signal,
      }),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchIntervalInBackground: false,
    refetchInterval: (query) => {
      if (
        !visible() ||
        !query.state.data?.items.some((item) => ['queued', 'running'].includes(item.state))
      )
        return false;
      return query.state.fetchFailureCount
        ? Math.min(1000 * 2 ** query.state.fetchFailureCount, 30_000)
        : 10_000;
    },
    retry: (failureCount, error) =>
      !(error instanceof ApiError && [401, 403, 404, 422].includes(error.status)) &&
      failureCount < 5,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
  });

  function onVisibilityChange(): void {
    if (document.visibilityState === 'hidden')
      void queryClient.cancelQueries({ queryKey: queryKey.value });
    else if (session.isAdministrator.value) void history.refetch();
  }
  onMounted(() => document.addEventListener('visibilitychange', onVisibilityChange));
  onBeforeUnmount(() => document.removeEventListener('visibilitychange', onVisibilityChange));

  return { history, state, offset, setState, pageSize: PAGE_SIZE };
}
