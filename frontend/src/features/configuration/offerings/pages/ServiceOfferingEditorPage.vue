<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Button from 'primevue/button';
import PageHeader from '../../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import type { ServiceOfferingDraft } from '../forms/serviceOfferingDraft';
import { useServiceOffering } from '../composables/useServiceOffering';
import ServiceOfferingForm from '../components/ServiceOfferingForm.vue';

const route = useRoute();
const router = useRouter();
const id = computed(() =>
  typeof route.params.id === 'string' && route.params.id !== 'new' ? route.params.id : undefined,
);
const isNew = computed(() => id.value === undefined);
const { detail, create, update, list } = useServiceOffering(id);
const initial = ref<ServiceOfferingDraft>({ name: '', description: '' });
async function refreshSaved() {
  if (!id.value) {
    const result = await list.refetch();
    if (result.isError || !result.data) throw new Error('List refresh failed');
    return null;
  }
  const result = await detail.refetch();
  if (result.isError || !result.data) throw new Error('No saved data');
  return result.data;
}
async function save(
  draft: ServiceOfferingDraft,
  patch: { name?: string | null; description?: string | null } | null,
) {
  if (id.value) {
    if (!patch) throw new Error('There are no changes to save.');
    return update.mutateAsync({ id: id.value, body: patch });
  }
  return create.mutateAsync(draft);
}
async function afterSave(saved: { id: string }): Promise<void> {
  if (!id.value) await router.replace(`/offerings/${saved.id}`);
}
</script>
<template>
  <section>
    <PageHeader
      :title="isNew ? 'Add service offering' : 'Edit service offering'"
      description="Enter a required name and description."
      ><Button
        label="Back to service offerings"
        severity="secondary"
        @click="router.push('/offerings')"
    /></PageHeader>
    <LoadingState v-if="!isNew && detail.isPending.value" message="Loading service offering…" />
    <ErrorState
      v-else-if="!isNew && detail.isError.value && !detail.data.value"
      message="This service offering is unavailable or could not be loaded. Return to the list and choose an available entry."
    />
    <ServiceOfferingForm
      v-else
      :key="id ?? 'new-offering'"
      :initial="
        id
          ? {
              name: detail.data.value?.name ?? '',
              description: detail.data.value?.description ?? '',
            }
          : initial
      "
      :existing="!isNew"
      :save="save"
      :refresh-saved="refreshSaved"
      :after-save="afterSave"
    />
  </section>
</template>
