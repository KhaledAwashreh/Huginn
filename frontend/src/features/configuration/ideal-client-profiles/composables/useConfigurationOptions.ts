import { computed } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import { useSession } from '../../../session/composables/useSession';
import { getConfigurationOptions } from '../api/getConfigurationOptions';

export function useConfigurationOptions() {
  const session = useSession();
  const query = useQuery({
    queryKey: computed(() => [
      'configuration',
      session.context.value?.account_id,
      session.context.value?.user_id,
      'collected-options',
    ]),
    enabled: computed(() => session.context.value !== null),
    queryFn: ({ signal }) => getConfigurationOptions(signal),
    retry: false,
  });
  return query;
}
