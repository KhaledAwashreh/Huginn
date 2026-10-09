import { computed, toValue, type MaybeRefOrGetter } from 'vue';
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { useSession } from '../../../session/composables/useSession';
import { createIdealClientProfile } from '../api/createIdealClientProfile';
import { deleteIdealClientProfile } from '../api/deleteIdealClientProfile';
import { getIdealClientProfile } from '../api/getIdealClientProfile';
import { listIdealClientProfiles } from '../api/listIdealClientProfiles';
import { updateIdealClientProfile } from '../api/updateIdealClientProfile';

export function useIdealClientProfile(
  id?: MaybeRefOrGetter<string | undefined>,
  offset: MaybeRefOrGetter<number> = 0,
  limit = 100,
) {
  const session = useSession();
  const queryClient = useQueryClient();
  const scope = computed(() => [session.context.value?.account_id, session.context.value?.user_id]);
  const invalidateAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ['configuration', ...scope.value, 'strategy-references'],
      }),
      queryClient.invalidateQueries({ queryKey: ['ideal-client-profiles', ...scope.value] }),
    ]);
  };
  const list = useQuery({
    queryKey: computed(() => ['ideal-client-profiles', ...scope.value, offset, limit]),
    enabled: computed(() => session.context.value !== null),
    queryFn: ({ signal }) => listIdealClientProfiles(toValue(offset), limit, signal),
    retry: false,
  });
  const detail = useQuery({
    queryKey: computed(() => ['ideal-client-profile', ...scope.value, toValue(id)]),
    enabled: computed(() => session.context.value !== null && Boolean(toValue(id))),
    queryFn: ({ signal }) => getIdealClientProfile(toValue(id) ?? '', signal),
    retry: false,
  });
  const create = useMutation({
    mutationFn: createIdealClientProfile,
    retry: false,
    onSuccess: invalidateAll,
  });
  const update = useMutation({
    mutationFn: ({
      id: itemId,
      body,
    }: {
      id: string;
      body: Parameters<typeof updateIdealClientProfile>[1];
    }) => updateIdealClientProfile(itemId, body),
    retry: false,
    onSuccess: (saved) => {
      queryClient.setQueryData(['ideal-client-profile', ...scope.value, saved.id], saved);
      return invalidateAll();
    },
  });
  const remove = useMutation({
    mutationFn: deleteIdealClientProfile,
    retry: false,
    onSuccess: invalidateAll,
  });
  return { list, detail, create, update, remove };
}
