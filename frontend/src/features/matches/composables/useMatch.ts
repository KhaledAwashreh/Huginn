import { computed, toValue, type MaybeRefOrGetter } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { getMatch } from '../api/getMatch';

export function useMatch(id: MaybeRefOrGetter<string | undefined>) {
  const session = useSession();
  const query = useQuery({
    queryKey: computed(() => [
      'matches',
      session.context.value?.account_id,
      session.context.value?.user_id,
      'detail',
      toValue(id),
    ]),
    enabled: computed(() => Boolean(session.context.value && toValue(id))),
    queryFn: ({ signal }) => getMatch(toValue(id) ?? '', signal),
  });
  return { query };
}
