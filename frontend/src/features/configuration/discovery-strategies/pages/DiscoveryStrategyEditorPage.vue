<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { components } from '../../../../api/generated/schema';
import PageHeader from '../../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import { useDiscoveryStrategy } from '../composables/useDiscoveryStrategy';
import { listDiscoveryStrategies } from '../api/listDiscoveryStrategies';
import { getDiscoveryStrategy } from '../api/getDiscoveryStrategy';
import type { DiscoveryStrategyDraft } from '../forms/discoveryStrategyDraft';
import DiscoveryStrategyForm from '../components/DiscoveryStrategyForm.vue';
const route = useRoute();
const router = useRouter();
const id = computed(() => (typeof route.params.id === 'string' ? route.params.id : undefined));
const creating = computed(() => !id.value);
const state = useDiscoveryStrategy(id);
const initial: DiscoveryStrategyDraft = {
  name: '',
  service_offering_id: '',
  ideal_client_profile_id: '',
  is_active: false,
};
async function save(
  draft: DiscoveryStrategyDraft,
  patch: components['schemas']['DiscoveryStrategyUpdateRequest'],
): Promise<DiscoveryStrategyDraft> {
  return creating.value ? state.create.mutateAsync(draft) : state.update.mutateAsync(patch);
}
async function refresh(): Promise<DiscoveryStrategyDraft | null> {
  if (creating.value) {
    await listDiscoveryStrategies();
    return null;
  }
  return getDiscoveryStrategy(id.value ?? '');
}
function saved(): void {
  if (creating.value) void router.push('/strategies');
}
</script>
<template>
  <PageHeader
    :title="creating ? 'Create strategy' : 'Edit strategy'"
    description="Link one service offering to one ideal client profile."
  />
  <DiscoveryStrategyForm
    v-if="creating"
    key="new"
    :initial="initial"
    :creating="true"
    :save="save"
    :refresh="refresh"
    @saved="saved"
  />
  <LoadingState v-else-if="state.query.isPending.value" />
  <ErrorState
    v-else-if="state.query.isError.value && !state.query.data.value"
    :message="state.query.error.value?.message ?? 'Strategy could not be loaded.'"
  />
  <DiscoveryStrategyForm
    v-else-if="state.query.data.value"
    :key="id ?? 'new'"
    :initial="state.query.data.value"
    :creating="false"
    :save="save"
    :refresh="refresh"
  />
</template>
