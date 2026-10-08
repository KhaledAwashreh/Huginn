import { computed } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { getAccountSecurity } from '../api/getAccountSecurity';

export function useAccountSecurity() {
  const session = useSession();
  return useQuery({
    queryKey: computed(() => [
      'account-security',
      session.context.value?.account_id,
      session.context.value?.user_id,
    ]),
    enabled: computed(() => session.context.value !== null),
    queryFn: ({ signal }) => getAccountSecurity(signal),
    retry: false,
  });
}
