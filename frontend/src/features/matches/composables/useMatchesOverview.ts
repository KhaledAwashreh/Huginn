import { computed } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { getMatchesOverview } from '../api/getMatchesOverview';

export function useMatchesOverview() {
  const session = useSession();
  const overview = useQuery({
    queryKey: computed(() => [
      'matches',
      session.context.value?.account_id,
      session.context.value?.user_id,
      'overview',
    ]),
    enabled: computed(() => Boolean(session.context.value)),
    queryFn: ({ signal }) => getMatchesOverview(signal),
  });
  return { overview };
}
