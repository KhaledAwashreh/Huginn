import { computed } from 'vue';
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { useSession } from '../../../session/composables/useSession';
import { getProfessionalProfile } from '../api/getProfessionalProfile';
import { updateProfessionalProfile } from '../api/updateProfessionalProfile';

export function useProfessionalProfile() {
  const session = useSession();
  const queryClient = useQueryClient();
  const queryKey = computed(() => [
    'professional-profile',
    session.context.value?.account_id,
    session.context.value?.user_id,
  ]);
  const profile = useQuery({
    queryKey,
    enabled: computed(() => session.context.value !== null),
    queryFn: ({ signal }) => getProfessionalProfile(signal),
    retry: false,
  });
  const save = useMutation({
    mutationFn: updateProfessionalProfile,
    retry: false,
    onSuccess: async (saved) => {
      queryClient.setQueryData(queryKey.value, saved);
      await queryClient.invalidateQueries({ queryKey: queryKey.value });
    },
  });
  return { profile, save };
}
