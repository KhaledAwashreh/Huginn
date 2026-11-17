import { computed } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import { useSession } from '../../../session/composables/useSession';
import { listDiscoveryStrategies } from '../api/listDiscoveryStrategies';

export function useActiveDiscoveryStrategies() {
  const session = useSession();
  const identity = computed(() =>
    [
      session.context.value?.account_id,
      session.context.value?.user_id,
      session.context.value?.csrf_token,
    ].join(':'),
  );
  const strategies = useQuery({
    queryKey: computed(() => ['prospecting', identity.value, 'strategies']),
    enabled: computed(() => Boolean(session.context.value)),
    queryFn: async ({ signal }) => {
      const items = [];
      let offset = 0;
      let more = true;
      while (more) {
        const page = await listDiscoveryStrategies(offset, 100, true, signal);
        items.push(...page.items);
        more = page.has_more;
        offset += page.limit;
      }
      return items;
    },
    retry: false,
  });
  const singleStrategy = computed(() => {
    if (strategies.isError.value || strategies.isPending.value) return null;
    const items = strategies.data.value;
    const only = items?.length === 1 ? items[0] : null;
    return only?.service_offering_id && only.ideal_client_profile_id ? only : null;
  });
  return { strategies, singleStrategy };
}
