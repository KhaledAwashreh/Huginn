import { computed } from 'vue';
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { useSession } from '../../../session/composables/useSession';
import { getAccount } from '../api/getAccount';
import { updateAccount } from '../api/updateAccount';

export function useAccount() {
  const session = useSession();
  const queryClient = useQueryClient();
  const queryKey = computed(() => [
    'account',
    session.context.value?.account_id,
    session.context.value?.user_id,
  ]);
  const account = useQuery({
    queryKey,
    enabled: computed(() => session.context.value !== null),
    queryFn: ({ signal }) => getAccount(signal),
    retry: false,
  });
  const save = useMutation({
    mutationFn: updateAccount,
    retry: false,
    onSuccess: async (saved) => {
      queryClient.setQueryData(queryKey.value, saved);
      await queryClient.invalidateQueries({ queryKey: queryKey.value });
    },
  });
  return { account, save };
}
