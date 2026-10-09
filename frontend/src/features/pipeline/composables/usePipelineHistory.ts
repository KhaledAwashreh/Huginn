import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { useSession } from '../../session/composables/useSession';
import {
  listInvocations,
  type InvocationStateFilter,
  type InvocationHistoryResponse,
} from '../api/listInvocations';

const PAGE_SIZE = 20;

function visible(): boolean {
  return typeof document === 'undefined' || document.visibilityState === 'visible';
}

function retry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && [401, 403, 404, 422].includes(error.status)) return false;
  return failureCount < 5;
}

export function usePipelineHistory() {
  const session = useSession();
  const pageVisible = ref(
    typeof document === 'undefined' || document.visibilityState === 'visible',
  );
  const queryClient = useQueryClient();
  const state = ref<InvocationStateFilter | undefined>();
  const offset = ref(0);
  const queryKey = computed(
    () =>
      [
        'admin',
        'pipeline',
        session.context.value?.account_id,
        'history',
        state.value ?? null,
        offset.value,
      ] as const,
  );
  const history = useQuery<InvocationHistoryResponse>({
    queryKey,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    enabled: computed(() => pageVisible.value && session.isAdministrator.value),
    queryFn: ({ signal }) =>
      listInvocations({
        limit: PAGE_SIZE,
        offset: offset.value,
        ...(state.value ? { state: state.value } : {}),
        signal,
      }),
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
    retry,
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

  function setState(next: InvocationStateFilter | undefined): void {
    state.value = next;
    offset.value = 0;
  }

  function previousPage(): void {
    offset.value = Math.max(0, offset.value - PAGE_SIZE);
  }

  function nextPage(): void {
    if (history.data.value?.has_more) offset.value += PAGE_SIZE;
  }

  return { history, state, offset, pageSize: PAGE_SIZE, setState, previousPage, nextPage };
}
