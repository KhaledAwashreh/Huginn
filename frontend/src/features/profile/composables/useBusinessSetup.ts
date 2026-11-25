import { computed } from 'vue';
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { getBusinessSetup } from '../api/getBusinessSetup';
import { saveBusinessSetup } from '../api/saveBusinessSetup';
import type { BusinessSetup, BusinessSetupRequest } from '../models/businessSetup';

export function useBusinessSetup() {
  const session = useSession();
  const client = useQueryClient();
  const identity = computed(() =>
    [
      session.context.value?.account_id,
      session.context.value?.user_id,
      session.context.value?.csrf_token,
    ].join(':'),
  );
  const queryKey = computed(() => ['business-setup', identity.value]);
  function owned(saved: BusinessSetup): BusinessSetup {
    if (
      saved.user.id !== session.context.value?.user_id ||
      saved.business.owner_user_id !== saved.user.id
    )
      throw new Error('Profile ownership could not be verified.');
    return saved;
  }
  const profile = useQuery({
    queryKey,
    enabled: computed(() => Boolean(session.context.value)),
    queryFn: async ({ signal }) => owned(await getBusinessSetup(signal)),
    retry: false,
  });
  const save = useMutation({
    mutationFn: async (body: BusinessSetupRequest) => {
      const requestedIdentity = identity.value;
      const saved = await saveBusinessSetup(body);
      if (requestedIdentity !== identity.value) throw new Error('The session changed.');
      return owned(saved);
    },
    retry: false,
    onSuccess: async (saved) => {
      const requestedIdentity = identity.value;
      const accountId = session.context.value?.account_id;
      const userId = session.context.value?.user_id;
      client.setQueryData(queryKey.value, saved);
      client.setQueryData(['account', accountId, userId], saved.user);
      await Promise.all([
        client.invalidateQueries({ queryKey: ['prospecting', requestedIdentity] }),
        client.invalidateQueries({ queryKey: ['configuration', accountId, userId] }),
        client.invalidateQueries({ queryKey: ['business-profile', accountId, userId] }),
      ]);
    },
  });
  return { profile, save, identity };
}
