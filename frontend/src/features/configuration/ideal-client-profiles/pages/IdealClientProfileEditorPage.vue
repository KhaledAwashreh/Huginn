<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Button from 'primevue/button';
import PageHeader from '../../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import type { IdealClientProfileDraft } from '../forms/idealClientProfileDraft';
import { useIdealClientProfile } from '../composables/useIdealClientProfile';
import IdealClientProfileForm from '../components/IdealClientProfileForm.vue';

const route = useRoute();
const router = useRouter();
const id = computed(() =>
  typeof route.params.id === 'string' && route.params.id !== 'new' ? route.params.id : undefined,
);
const isNew = computed(() => id.value === undefined);
const { detail, create, update, list } = useIdealClientProfile(id);
const emptyDraft: IdealClientProfileDraft = {
  name: '',
  industries: [],
  company_sizes: [],
  geographies: [],
  exclusions: [],
};
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
  draft: IdealClientProfileDraft,
  patch: {
    name?: string | null;
    industries?: IdealClientProfileDraft['industries'] | null;
    company_sizes?: IdealClientProfileDraft['company_sizes'] | null;
    geographies?: IdealClientProfileDraft['geographies'] | null;
    exclusions?: IdealClientProfileDraft['exclusions'] | null;
  } | null,
) {
  if (id.value) {
    if (!patch) throw new Error('There are no changes to save.');
    return update.mutateAsync({ id: id.value, body: patch });
  }
  return create.mutateAsync(draft);
}
async function afterSave(saved: { id: string }): Promise<void> {
  if (!id.value) await router.replace(`/icps/${saved.id}`);
}
</script>
<template>
  <section>
    <PageHeader
      :title="isNew ? 'Add ideal client profile' : 'Edit ideal client profile'"
      description="Build structured targeting criteria and exclusions."
      ><Button label="Back to ICPs" severity="secondary" @click="router.push('/icps')"
    /></PageHeader>
    <LoadingState v-if="!isNew && detail.isPending.value" message="Loading ICP…" />
    <ErrorState
      v-else-if="!isNew && detail.isError.value && !detail.data.value"
      message="This ICP is unavailable or could not be loaded. Return to the list and choose an available entry."
    />
    <IdealClientProfileForm
      v-else
      :key="id ?? 'new-icp'"
      :initial="
        id && detail.data.value
          ? {
              name: detail.data.value.name,
              industries: detail.data.value.industries.map(({ name }) => ({ name })),
              company_sizes: detail.data.value.company_sizes.map(({ band }) => ({ band })),
              geographies: detail.data.value.geographies.map(({ kind, value }) => ({
                kind,
                value,
              })),
              exclusions: detail.data.value.exclusions.map((item) =>
                item.kind === 'company'
                  ? { kind: item.kind, company_id: item.company_id }
                  : item.kind === 'industry'
                    ? { kind: item.kind, name: item.name }
                    : {
                        kind: item.kind,
                        geography: { kind: item.geography.kind, value: item.geography.value },
                      },
              ),
            }
          : emptyDraft
      "
      :existing="!isNew"
      :save="save"
      :refresh-saved="refreshSaved"
      :after-save="afterSave"
    />
  </section>
</template>
