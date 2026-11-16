import { computed } from 'vue';
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { getBusinessProfile } from '../api/getBusinessProfile';
import { updateBusinessProfile } from '../api/updateBusinessProfile';

export function useBusinessProfile() {
  const session = useSession();
  const queryClient = useQueryClient();
  const queryKey = computed(() => [
    'business-profile',
    session.context.value?.account_id,
    session.context.value?.user_id,
  ]);
  const business = useQuery({
    queryKey,
    enabled: computed(() => session.context.value !== null),
    queryFn: async ({ signal }) => {
      const saved = await getBusinessProfile(signal);
      if (saved.owner_user_id !== session.context.value?.user_id)
        throw new Error('Business profile ownership could not be verified.');
      return saved;
    },
    retry: false,
  });
  const save = useMutation({
    mutationFn: updateBusinessProfile,
    retry: false,
    onSuccess: async (saved) => {
      if (saved.owner_user_id !== session.context.value?.user_id) return;
      queryClient.setQueryData(queryKey.value, saved);
    },
  });
  return { business, save };
}
