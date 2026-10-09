import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { useSession } from '../../session/composables/useSession';
import { getInvocation, type InvocationDetailResponse } from '../api/getInvocation';

function visible(): boolean {
  return typeof document === 'undefined' || document.visibilityState === 'visible';
}

function retry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && [401, 403, 404, 422].includes(error.status)) return false;
  return failureCount < 5;
}

export function usePipelineInvocation(invocationId: () => string) {
  const session = useSession();
  const pageVisible = ref(
    typeof document === 'undefined' || document.visibilityState === 'visible',
  );
  const queryClient = useQueryClient();
  const id = computed(invocationId);
  const queryKey = computed(
    () => ['admin', 'pipeline', session.context.value?.account_id, 'invocation', id.value] as const,
  );
  const invocation = useQuery<InvocationDetailResponse>({
    queryKey,
    staleTime: (query) =>
      query.state.data && !['queued', 'running'].includes(query.state.data.state) ? Infinity : 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    enabled: computed(
      () => pageVisible.value && session.isAdministrator.value && id.value.length > 0,
    ),
    queryFn: ({ signal }) => getInvocation(id.value, signal),
    refetchInterval: (query) => {
      if (!visible() || !['queued', 'running'].includes(query.state.data?.state ?? ''))
        return false;
      return query.state.fetchFailureCount
        ? Math.min(1000 * 2 ** query.state.fetchFailureCount, 30_000)
        : 3000;
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

  watch(
    () => invocation.data.value,
    (next, previous) => {
      if (!next) return;
      const goldState = (value: typeof next | undefined) => {
        const stage = value?.stages.find((item) => item.name === 'gold.company');
        return JSON.stringify([stage?.state, stage?.metrics]);
      };
      const goldChanged = Boolean(previous) && goldState(next) !== goldState(previous);
      const becameTerminal = Boolean(
        previous &&
        ['queued', 'running'].includes(previous.state) &&
        !['queued', 'running'].includes(next.state),
      );
      if (goldChanged || becameTerminal) {
        void queryClient.invalidateQueries({
          queryKey: ['admin', 'pipeline', session.context.value?.account_id, 'companies', id.value],
        });
      }
    },
  );

  return { invocation, queryKey };
}
