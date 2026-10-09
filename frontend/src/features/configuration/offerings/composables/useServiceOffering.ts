import { computed, toValue, type MaybeRefOrGetter } from 'vue';
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { useSession } from '../../../session/composables/useSession';
import { createServiceOffering } from '../api/createServiceOffering';
import { deleteServiceOffering } from '../api/deleteServiceOffering';
import { getServiceOffering } from '../api/getServiceOffering';
import { listServiceOfferings } from '../api/listServiceOfferings';
import { updateServiceOffering } from '../api/updateServiceOffering';

export function useServiceOffering(
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
      queryClient.invalidateQueries({ queryKey: ['service-offerings', ...scope.value] }),
    ]);
  };
  const list = useQuery({
    queryKey: computed(() => ['service-offerings', ...scope.value, offset, limit]),
    enabled: computed(() => session.context.value !== null),
    queryFn: ({ signal }) => listServiceOfferings(toValue(offset), limit, signal),
    retry: false,
  });
  const detail = useQuery({
    queryKey: computed(() => ['service-offering', ...scope.value, toValue(id)]),
    enabled: computed(() => session.context.value !== null && Boolean(toValue(id))),
    queryFn: ({ signal }) => getServiceOffering(toValue(id) ?? '', signal),
    retry: false,
  });
  const create = useMutation({
    mutationFn: createServiceOffering,
    retry: false,
    onSuccess: invalidateAll,
  });
  const update = useMutation({
    mutationFn: ({
      id: itemId,
      body,
    }: {
      id: string;
      body: Parameters<typeof updateServiceOffering>[1];
    }) => updateServiceOffering(itemId, body),
    retry: false,
    onSuccess: (saved) => {
      queryClient.setQueryData(['service-offering', ...scope.value, saved.id], saved);
      return invalidateAll();
    },
  });
  const remove = useMutation({
    mutationFn: deleteServiceOffering,
    retry: false,
    onSuccess: invalidateAll,
  });
  return { list, detail, create, update, remove };
}
