import { computed, onBeforeUnmount, onMounted } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { useSession } from '../../session/composables/useSession';
import { listTargetUsers } from '../api/listTargetUsers';

const PAGE_SIZE = 20;

export function useTargetUsers(search: () => string, offset: () => number) {
  const session = useSession();
  const queryClient = useQueryClient();
  const normalizedSearch = computed(() => search().trim());
  const currentOffset = computed(offset);
  const queryKey = computed(
    () =>
      [
        'admin',
        'matchmaking',
        session.context.value?.account_id,
        'target-users',
        normalizedSearch.value,
        currentOffset.value,
      ] as const,
  );
  const users = useQuery({
    queryKey,
    enabled: computed(() => session.isAdministrator.value),
    queryFn: ({ signal }) =>
      listTargetUsers({
        search: normalizedSearch.value,
        offset: currentOffset.value,
        limit: PAGE_SIZE,
        signal,
      }),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: (failureCount, error) =>
      !(error instanceof ApiError && [401, 403, 404, 422].includes(error.status)) &&
      failureCount < 5,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
  });

  function onVisibilityChange(): void {
    if (document.visibilityState === 'hidden')
      void queryClient.cancelQueries({ queryKey: queryKey.value });
    else if (session.isAdministrator.value) void users.refetch();
  }
  onMounted(() => document.addEventListener('visibilitychange', onVisibilityChange));
  onBeforeUnmount(() => document.removeEventListener('visibilitychange', onVisibilityChange));

  return { users, pageSize: PAGE_SIZE };
}
