<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { components } from '../../../../api/generated/schema';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import { useIdealClientProfile } from '../composables/useIdealClientProfile';
import type { IdealClientProfileDraft } from '../forms/idealClientProfileDraft';
import type { IcpClientAnnotation, IcpFeedbackAnnotation } from '../models/icpAnnotations';
import IdealClientProfileForm from './IdealClientProfileForm.vue';

const props = defineProps<{
  clients: IcpClientAnnotation[];
  reactions: IcpFeedbackAnnotation[];
  selectedIcpId?: string | undefined;
}>();
const pinnedIcpId = ref(props.selectedIcpId);
const creating = ref(false);
const { list, detail, create, update } = useIdealClientProfile(() => pinnedIcpId.value);
const form = ref<InstanceType<typeof IdealClientProfileForm> | null>(null);

const items = computed(() => list.data.value?.items ?? []);
if (!props.selectedIcpId && list.data.value?.items.length === 0) creating.value = true;
watch(
  [() => props.selectedIcpId, () => list.data.value],
  ([requestedId, page], previous) => {
    const previousId = previous?.[0];
    if (requestedId !== previousId) {
      pinnedIcpId.value = requestedId ?? page?.items[0]?.id;
      creating.value = !requestedId && page !== undefined && page.items.length === 0;
      return;
    }
    if (requestedId) {
      pinnedIcpId.value = requestedId;
      creating.value = false;
      return;
    }
    if (pinnedIcpId.value || creating.value || !page) return;
    if (page.items[0]) pinnedIcpId.value = page.items[0].id;
    else creating.value = true;
  },
  { immediate: true },
);
const query = computed(() => (pinnedIcpId.value && !creating.value ? detail : list));
const icp = computed(() => (creating.value ? undefined : detail.data.value));
const initial = computed<IdealClientProfileDraft>(() => {
  const current = icp.value;
  if (!current) {
    return { name: '', industries: [], company_sizes: [], geographies: [], exclusions: [] };
  }
  return {
    name: current.name,
    industries: current.industries.map(({ name }) => ({ name })),
    company_sizes: current.company_sizes.map(({ band }) => ({ band })),
    geographies: current.geographies.map(({ kind, value }) => ({ kind, value })),
    exclusions: current.exclusions.map((item) =>
      item.kind === 'company'
        ? { kind: item.kind, company_id: item.company_id }
        : item.kind === 'industry'
          ? { kind: item.kind, name: item.name }
          : {
              kind: item.kind,
              geography: { kind: item.geography.kind, value: item.geography.value },
            },
    ),
  };
});

async function refreshSaved() {
  if (creating.value) {
    const result = await list.refetch();
    if (result.isError || !result.data) throw new Error('List refresh failed');
    // A list refresh cannot identify which row was committed by an uncertain
    // create, so keep the new-draft identity and require explicit recovery.
    return null;
  }
  if (pinnedIcpId.value) {
    const result = await detail.refetch();
    if (result.isError || !result.data) throw new Error('ICP refresh failed');
    return result.data;
  }
  const result = await list.refetch();
  if (result.isError || !result.data) throw new Error('List refresh failed');
  return null;
}
async function save(
  draft: IdealClientProfileDraft,
  patch: Parameters<typeof update.mutateAsync>[0]['body'] | null,
) {
  if (creating.value) return create.mutateAsync(draft);
  const id = pinnedIcpId.value;
  if (!id) throw new Error('No ICP is selected for editing.');
  if (!patch) throw new Error('There are no changes to save.');
  return update.mutateAsync({ id, body: patch });
}

function afterSave(saved: components['schemas']['IdealClientProfileResponse']): void {
  if (!creating.value) return;
  creating.value = false;
  pinnedIcpId.value = saved.id;
}

defineExpose({ canClose: () => form.value?.canClose() ?? true });
</script>

<template>
  <div class="icp-definition">
    <LoadingState v-if="query.isPending.value" message="Loading your ICP definition…" />
    <ErrorState
      v-else-if="query.isError.value && !query.data.value"
      message="Your ICP definition could not be loaded."
    />
    <template v-else>
      <p v-if="!props.selectedIcpId && items.length > 1 && !creating" class="annotations-empty">
        Editing {{ icp?.name }}. Choose a different ICP from Profile.
      </p>
      <IdealClientProfileForm
        ref="form"
        :key="creating ? 'new-icp' : (pinnedIcpId ?? 'unselected-icp')"
        :initial="initial"
        :existing="!creating && Boolean(icp)"
        :save="save"
        :refresh-saved="refreshSaved"
        :after-save="afterSave"
      />
    </template>
    <section v-if="clients.length" class="annotations" aria-labelledby="client-signals-heading">
      <h2 id="client-signals-heading">From your client list</h2>
      <ul>
        <li v-for="client in clients" :key="client.name">
          <strong>{{ client.idealExample ? 'Ideal client:' : 'Past client:' }}</strong>
          {{ client.name
          }}{{
            [client.industry, client.stage, client.size, client.location].some(Boolean)
              ? ` (${[client.industry, client.stage, client.size, client.location].filter(Boolean).join(', ')})`
              : ''
          }}
        </li>
      </ul>
    </section>
    <section v-if="reactions.length" class="annotations" aria-labelledby="annotations-heading">
      <h2 id="annotations-heading">From your feedback</h2>
      <ul>
        <li v-for="reaction in reactions" :key="reaction.matchId">
          <template v-if="reaction.kind === 'up'">
            <strong>Good match:</strong> {{ reaction.companyName }}
          </template>
          <template v-else>
            <strong>Not a fit:</strong> {{ reaction.companyName }} ({{
              reaction.reasonLabel ?? 'No reason given'
            }})<template v-if="reaction.note">. {{ reaction.note }}</template>
          </template>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.icp-definition {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}
.annotations {
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
h2 {
  margin: 0 0 var(--space-3);
  font-size: 1rem;
  font-weight: 600;
}
ul {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding-left: var(--space-5);
}
.annotations-empty {
  margin: 0;
  color: var(--color-text-muted);
}
</style>
