<script setup lang="ts">
import { ref, watchEffect } from 'vue';
import Button from 'primevue/button';
import { RouterLink } from 'vue-router';
import { useActiveDiscoveryStrategies } from '../../discovery-strategies/composables/useActiveDiscoveryStrategies';
import { useIdealClientProfile } from '../composables/useIdealClientProfile';
import IcpDefinitionPanel from './IcpDefinitionPanel.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import type { IcpClientAnnotation, IcpFeedbackAnnotation } from '../models/icpAnnotations';

defineProps<{ clients: IcpClientAnnotation[]; reactions: IcpFeedbackAnnotation[] }>();
const emit = defineEmits<{ setup: [] }>();
const { strategies, singleStrategy } = useActiveDiscoveryStrategies();
const { list } = useIdealClientProfile();
const panel = ref<InstanceType<typeof IcpDefinitionPanel> | null>(null);
// Once opened, the editor owns its create/update intent until Settings closes.
const editor = ref<{ icpId: string | null } | null>(null);
watchEffect(() => {
  if (
    editor.value ||
    strategies.isPending.value ||
    list.isPending.value ||
    strategies.isError.value ||
    list.isError.value
  )
    return;
  if (singleStrategy.value) editor.value = { icpId: singleStrategy.value.ideal_client_profile_id };
  else if (list.data.value?.items.length === 0 && !list.data.value.has_more)
    editor.value = { icpId: null };
});
defineExpose({ canClose: () => panel.value?.canClose() ?? true });
</script>
<template>
  <IcpDefinitionPanel
    v-if="editor"
    ref="panel"
    :selected-icp-id="editor.icpId ?? undefined"
    :clients="clients"
    :reactions="reactions"
  />
  <LoadingState
    v-else-if="strategies.isPending.value || list.isPending.value"
    message="Loading discovery setup…"
  />
  <ErrorState
    v-else-if="strategies.isError.value || list.isError.value"
    message="Discovery setup could not be loaded."
  >
    <Button
      label="Retry discovery setup"
      @click="
        strategies.refetch();
        list.refetch();
      "
    />
  </ErrorState>
  <div v-else>
    <p>Choose your service offering and ICP in Profile before editing your discovery setup.</p>
    <RouterLink to="/profile" @click="emit('setup')">Set up discovery in Profile</RouterLink>
  </div>
</template>
