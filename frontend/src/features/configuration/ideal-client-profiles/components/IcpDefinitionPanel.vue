<script setup lang="ts">
import { computed, ref } from 'vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import { useIdealClientProfile } from '../composables/useIdealClientProfile';
import type { IdealClientProfileDraft } from '../forms/idealClientProfileDraft';
import type { IcpClientAnnotation, IcpFeedbackAnnotation } from '../models/icpAnnotations';
import IdealClientProfileForm from './IdealClientProfileForm.vue';

defineProps<{ clients: IcpClientAnnotation[]; reactions: IcpFeedbackAnnotation[] }>();
const { list, create, update } = useIdealClientProfile();
const form = ref<InstanceType<typeof IdealClientProfileForm> | null>(null);

// Each business has one ICP for now; accounts with more edit their first.
const items = computed(() => list.data.value?.items ?? []);
const icp = computed(() => items.value[0]);
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
  const result = await list.refetch();
  if (result.isError || !result.data) throw new Error('List refresh failed');
  return result.data.items[0] ?? null;
}
async function save(
  draft: IdealClientProfileDraft,
  patch: Parameters<typeof update.mutateAsync>[0]['body'] | null,
) {
  const id = icp.value?.id;
  if (!id) return create.mutateAsync(draft);
  if (!patch) throw new Error('There are no changes to save.');
  return update.mutateAsync({ id, body: patch });
}

defineExpose({ canClose: () => form.value?.canClose() ?? true });
</script>

<template>
  <div class="icp-definition">
    <LoadingState v-if="list.isPending.value" message="Loading your ICP definition…" />
    <ErrorState v-else-if="list.isError.value" message="Your ICP definition could not be loaded." />
    <template v-else>
      <p v-if="items.length > 1" class="annotations-empty">
        You have {{ items.length }} ICPs. This edits the first one, {{ icp?.name }}.
      </p>
      <IdealClientProfileForm
        ref="form"
        :key="icp?.id ?? 'new-icp'"
        :initial="initial"
        :existing="Boolean(icp)"
        :save="save"
        :refresh-saved="refreshSaved"
        :after-save="() => undefined"
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
