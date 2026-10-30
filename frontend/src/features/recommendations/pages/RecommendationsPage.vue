<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  onBeforeRouteLeave,
  onBeforeRouteUpdate,
  useRoute,
  useRouter,
  RouterLink,
} from 'vue-router';
import { useQueryClient } from '@tanstack/vue-query';
import Button from 'primevue/button';
import Select from 'primevue/select';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import RecommendationList from '../components/RecommendationList.vue';
import { useRecommendations } from '../composables/useRecommendations';
import type { RecommendationFeedback } from '../models/recommendationFeedback';
const route = useRoute();
const router = useRouter();
const requestedBatch = computed(() =>
  typeof route.query.batch === 'string' ? route.query.batch : '',
);
const weekly = computed(() => route.path === '/weekly-matches');
const workspace = useRecommendations(requestedBatch, weekly);
watch(
  () => route.query.strategy,
  (value) => {
    if (!weekly.value && !requestedBatch.value && typeof value === 'string')
      workspace.strategyId.value = value;
  },
  { immediate: true },
);
const displayedBatch = computed(() => {
  const batch = workspace.batch.data.value;
  if (!batch || !weekly.value || typeof route.query.strategy !== 'string') return batch;
  return {
    ...batch,
    items: batch.items.filter((item) =>
      item.strategies?.some((strategy) => strategy.id === route.query.strategy),
    ),
  };
});
function selectWeek(value: string) {
  if (!canLeave()) return;
  dirty.value = {};
  void router.replace({ query: { ...route.query, batch: value } });
}
function changeHistoryPage(direction: number) {
  if (!canLeave()) return;
  dirty.value = {};
  workspace.pinnedBatch.value = '';
  workspace.historyOffset.value = Math.max(0, workspace.historyOffset.value + direction * 12);
  clearBatchLink();
}
const client = useQueryClient();
const dirty = ref<Record<string, boolean>>({});
watch(workspace.identity, () => {
  dirty.value = {};
});
const hasDirty = computed(() => Object.values(dirty.value).some(Boolean));
function canLeave() {
  return !hasDirty.value || window.confirm('Discard your unsaved feedback?');
}
onBeforeRouteLeave(canLeave);
onBeforeRouteUpdate((to, from) => {
  if (to.query.batch === from.query.batch && to.query.strategy === from.query.strategy) return true;
  if (!canLeave()) return false;
  dirty.value = {};
  return true;
});
function clearBatchLink() {
  if (!route.query.batch) return;
  const query = { ...route.query };
  delete query.batch;
  void router.replace({ query });
}
function selectStrategy(value: string) {
  if (!canLeave()) return;
  dirty.value = {};
  workspace.pinnedBatch.value = '';
  workspace.strategyId.value = value;
  clearBatchLink();
}
async function generate() {
  if (!canLeave()) return;
  if (await workspace.generate()) {
    dirty.value = {};
    clearBatchLink();
  }
}
async function saved(entry: RecommendationFeedback) {
  if (entry.batch_id !== workspace.batch.data.value?.id) return;
  const key = [...workspace.feedbackKey.value];
  if (!workspace.feedback.isSuccess.value) {
    await client.invalidateQueries({ queryKey: key });
    return;
  }
  await client.cancelQueries({ queryKey: key });
  if (entry.batch_id !== workspace.batch.data.value?.id) return;
  client.setQueryData<RecommendationFeedback[]>(key, (previous) =>
    previous?.some((value) => value.id === entry.id) ? previous : [...(previous ?? []), entry],
  );
}
</script>
<template>
  <div class="recommendations-page">
    <PageHeader
      :title="weekly ? 'Weekly Matches' : 'Recommendations'"
      :description="
        weekly
          ? 'Up to seven companies selected automatically each week across your active strategies. These are the selections prepared for your weekly email.'
          : 'Explore outreach recommendations on demand for a selected active discovery strategy.'
      "
    />
    <p class="guidance">
      Scores indicate research relevance. Source overlap does not prove buying intent. Confirm the
      company’s needs and buying role before outreach.
    </p>
    <RouterLink v-if="weekly" to="/matches">Earlier match history, notes and statuses</RouterLink>
    <LoadingState
      v-if="!weekly && workspace.strategies.isPending.value && !workspace.strategies.data.value"
      message="Loading discovery strategies…"
    />
    <ErrorState
      v-else-if="!weekly && workspace.strategies.isError.value && !workspace.strategies.data.value"
      message="Discovery strategies could not be loaded."
      ><Button label="Retry strategies" @click="workspace.strategies.refetch()"
    /></ErrorState>
    <LoadingState
      v-else-if="weekly && workspace.weeklyHistory.isPending.value && !workspace.pinnedBatch.value"
      message="Loading weekly history…"
    />
    <ErrorState
      v-else-if="weekly && workspace.weeklyHistory.isError.value && !workspace.pinnedBatch.value"
      message="Weekly history could not be loaded."
      ><Button label="Retry weekly history" @click="workspace.weeklyHistory.refetch()"
    /></ErrorState>
    <template
      v-else-if="weekly || workspace.strategies.data.value?.length || workspace.pinnedBatch.value"
    >
      <ErrorState
        v-if="!weekly && workspace.strategies.isError.value"
        message="Discovery strategies could not be refreshed. Previously received strategies remain available."
      />
      <ErrorState
        v-if="weekly && workspace.weeklyHistory.isError.value"
        message="Weekly history could not be loaded. Showing the linked saved selection."
        ><Button label="Retry weekly history" @click="workspace.weeklyHistory.refetch()"
      /></ErrorState>
      <div v-if="weekly" class="toolbar">
        <div class="field">
          <label for="weekly-selection">Weekly selection</label>
          <Select
            input-id="weekly-selection"
            aria-label="Weekly selection"
            :model-value="workspace.pinnedBatch.value"
            :options="
              (workspace.weeklyHistory.data.value ?? []).map((batch) => ({
                id: batch.id,
                label: new Date(batch.created_at).toLocaleDateString(),
              }))
            "
            option-label="label"
            option-value="id"
            placeholder="No weekly selections yet"
            @update:model-value="selectWeek"
          />
        </div>
        <Button
          label="Newer weeks"
          severity="secondary"
          :disabled="workspace.historyOffset.value === 0"
          @click="changeHistoryPage(-1)"
        />
        <Button
          label="Older weeks"
          severity="secondary"
          :disabled="(workspace.weeklyHistory.data.value?.length ?? 0) < 12"
          @click="changeHistoryPage(1)"
        />
      </div>
      <div v-else class="toolbar">
        <div class="field">
          <label for="recommendation-strategy">Discovery strategy</label
          ><Select
            input-id="recommendation-strategy"
            aria-label="Discovery strategy"
            :model-value="workspace.strategyId.value"
            :options="workspace.strategies.data.value ?? []"
            option-label="name"
            option-value="id"
            placeholder="Choose a strategy"
            @update:model-value="selectStrategy"
          />
        </div>
        <Button
          :label="
            workspace.generating.value ? 'Generating recommendations…' : 'Generate recommendations'
          "
          :disabled="
            !workspace.strategyId.value ||
            workspace.generating.value ||
            workspace.batch.isFetching.value
          "
          @click="generate"
        />
      </div>
      <RouterLink
        v-if="!weekly && workspace.strategyId.value"
        :to="{ path: '/weekly-matches', query: { strategy: workspace.strategyId.value } }"
        >View Weekly Matches for this strategy</RouterLink
      >
      <RouterLink v-if="weekly && route.query.strategy" to="/weekly-matches"
        >Show matches across all strategies</RouterLink
      >
      <ErrorState
        v-if="workspace.generationError.value"
        :message="workspace.generationError.value"
      />
      <EmptyState
        v-if="!workspace.pinnedBatch.value && (weekly || !workspace.strategyId.value)"
        :message="
          weekly
            ? 'Weekly Matches appear automatically after your first scheduled email. You can explore Recommendations while you wait.'
            : 'Choose a strategy to resume its latest recommendations or generate a new list.'
        "
      />
      <LoadingState
        v-else-if="workspace.batch.isFetching.value && !workspace.batch.data.value"
        message="Loading research recommendations…"
      />
      <ErrorState
        v-else-if="workspace.batch.isError.value && !workspace.batch.data.value"
        :message="
          workspace.pinnedBatch.value
            ? 'This saved assessment could not be loaded. It may be unavailable.'
            : 'The latest recommendations could not be loaded.'
        "
        ><Button label="Retry recommendations" @click="workspace.batch.refetch()"
      /></ErrorState>
      <template v-else-if="workspace.batch.data.value">
        <ErrorState
          v-if="workspace.batch.isError.value"
          message="Recommendations could not be refreshed. Showing the previously received assessment."
        />
        <p class="batch-context">
          Generated
          <time :datetime="workspace.batch.data.value.created_at">{{
            new Date(workspace.batch.data.value.created_at).toLocaleString()
          }}</time>
          · {{ workspace.batch.data.value.candidate_count }} candidates assessed
          <span class="batch-reference"
            >Assessment reference: {{ workspace.batch.data.value.id }}</span
          >
        </p>
        <ErrorState
          v-if="workspace.feedback.isError.value"
          message="Feedback history could not be loaded."
          ><Button label="Retry feedback history" @click="workspace.feedback.refetch()"
        /></ErrorState>
        <EmptyState
          v-if="!displayedBatch?.items.length"
          :message="
            weekly
              ? 'No companies were selected for this strategy in this weekly batch.'
              : 'This assessment returned no recommendations. Review your strategy or try again when new source evidence is available.'
          "
        />
        <RecommendationList
          v-else
          :key="`${workspace.identity.value}:${workspace.batch.data.value.id}`"
          :inert="workspace.generating.value || workspace.batch.isFetching.value"
          :batch="displayedBatch!"
          :feedback="workspace.feedback.data.value ?? []"
          :feedback-available="workspace.feedback.isSuccess.value"
          @saved="saved"
          @dirty="
            (id, value) => {
              dirty[id] = value;
            }
          "
        />
      </template>
      <EmptyState
        v-else
        message="No saved recommendations for this strategy yet. Generate recommendations to begin your research."
      />
    </template>
    <EmptyState
      v-else
      message="Add an active discovery strategy in Business setup to generate recommendations."
    />
  </div>
</template>
<style scoped>
.recommendations-page {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}
.guidance {
  margin: 0;
  padding: var(--space-4);
  background: var(--color-surface-muted);
  border-left: 3px solid var(--color-primary);
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  align-items: end;
}
.field {
  display: grid;
  gap: var(--space-2);
  min-width: min(100%, 280px);
  max-width: 100%;
  flex: 1;
}
.batch-reference {
  display: block;
  overflow-wrap: anywhere;
}
.batch-context {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}
</style>
