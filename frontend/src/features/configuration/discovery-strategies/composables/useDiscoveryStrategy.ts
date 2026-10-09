import { computed, toValue, type MaybeRefOrGetter } from 'vue';
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query';
import type { components } from '../../../../api/generated/schema';
import { useSession } from '../../../session/composables/useSession';
import { getDiscoveryStrategy } from '../api/getDiscoveryStrategy';
import { createDiscoveryStrategy } from '../api/createDiscoveryStrategy';
import { updateDiscoveryStrategy } from '../api/updateDiscoveryStrategy';
import { deleteDiscoveryStrategy } from '../api/deleteDiscoveryStrategy';
export function useDiscoveryStrategy(id: MaybeRefOrGetter<string | undefined>) {
  const session = useSession();
  const client = useQueryClient();
  const key = computed(() => [
    'configuration',
    session.context.value?.account_id,
    session.context.value?.user_id,
    'strategies',
  ]);
  const query = useQuery({
    queryKey: computed(() => [...key.value, toValue(id)]),
    enabled: computed(() => Boolean(session.context.value && toValue(id))),
    queryFn: ({ signal }) => getDiscoveryStrategy(toValue(id) ?? '', signal),
    retry: false,
  });
  const invalidate = () => client.invalidateQueries({ queryKey: key.value });
  const create = useMutation({
    mutationFn: createDiscoveryStrategy,
    retry: false,
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: (body: components['schemas']['DiscoveryStrategyUpdateRequest']) =>
      updateDiscoveryStrategy(toValue(id) ?? '', body),
    retry: false,
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: deleteDiscoveryStrategy,
    retry: false,
    onSuccess: invalidate,
  });
  return { query, create, update, remove };
}
