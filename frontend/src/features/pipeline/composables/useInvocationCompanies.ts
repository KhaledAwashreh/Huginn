import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { useSession } from '../../session/composables/useSession';
import { listInvocationCompanies } from '../api/listInvocationCompanies';

const PAGE_SIZE = 50;

export function useInvocationCompanies(
  invocationId: () => string,
  state: () => string | undefined,
) {
  const session = useSession();
  const pageVisible = ref(
    typeof document === 'undefined' || document.visibilityState === 'visible',
  );
  const queryClient = useQueryClient();
  const id = computed(invocationId);
  const offset = ref(0);
  const queryKey = computed(
    () =>
      [
        'admin',
        'pipeline',
        session.context.value?.account_id,
        'companies',
        id.value,
        offset.value,
      ] as const,
  );
  const companies = useQuery({
    queryKey,
    staleTime: () => (state() && !['queued', 'running'].includes(state() ?? '') ? Infinity : 0),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    enabled: computed(
      () => pageVisible.value && session.isAdministrator.value && id.value.length > 0,
    ),
    queryFn: ({ signal }) =>
      listInvocationCompanies({
        invocationId: id.value,
        limit: PAGE_SIZE,
        offset: offset.value,
        signal,
      }),
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
    offset.value = 0;
  });

  function previousPage(): void {
    offset.value = Math.max(0, offset.value - PAGE_SIZE);
  }

  function nextPage(): void {
    if (companies.data.value?.has_more) offset.value += PAGE_SIZE;
  }

  return { companies, offset, pageSize: PAGE_SIZE, previousPage, nextPage };
}
