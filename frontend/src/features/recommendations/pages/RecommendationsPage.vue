<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
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
const workspace = useRecommendations();
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
function selectStrategy(value: string) {
  if (!canLeave()) return;
  dirty.value = {};
  workspace.strategyId.value = value;
}
async function generate() {
  if (!canLeave()) return;
  dirty.value = {};
  await workspace.generate();
}
async function saved(entry: RecommendationFeedback) {
  if (entry.batch_id !== workspace.batch.data.value?.id) return;
  const key = [...workspace.feedbackKey.value];
  await client.cancelQueries({ queryKey: key });
  if (entry.batch_id !== workspace.batch.data.value?.id) return;
  client.setQueryData<RecommendationFeedback[]>(key, (previous) => [...(previous ?? []), entry]);
}
</script>
<template>
  <div class="recommendations-page">
    <PageHeader
      title="Research recommendations"
      description="Review companies for your discovery strategy, assess the evidence, and record what happens next."
    />
    <p class="guidance">
      Scores indicate research relevance. Source overlap does not prove buying intent. Confirm the
      company’s needs and buying role before outreach.
    </p>
    <LoadingState
      v-if="workspace.strategies.isPending.value && !workspace.strategies.data.value"
      message="Loading discovery strategies…"
    />
    <ErrorState
      v-else-if="workspace.strategies.isError.value && !workspace.strategies.data.value"
      message="Discovery strategies could not be loaded."
      ><Button label="Retry strategies" @click="workspace.strategies.refetch()"
    /></ErrorState>
    <template v-else-if="workspace.strategies.data.value?.length">
      <ErrorState
        v-if="workspace.strategies.isError.value"
        message="Discovery strategies could not be refreshed. Previously received strategies remain available."
      />
      <div class="toolbar">
        <div class="field">
          <label for="recommendation-strategy">Discovery strategy</label
          ><Select
            input-id="recommendation-strategy"
            aria-label="Discovery strategy"
            :model-value="workspace.strategyId.value"
            :options="workspace.strategies.data.value"
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
      <ErrorState
        v-if="workspace.generationError.value"
        :message="workspace.generationError.value"
      />
      <EmptyState
        v-if="!workspace.strategyId.value"
        message="Choose a strategy to resume its latest recommendations or generate a new list."
      />
      <LoadingState
        v-else-if="workspace.batch.isFetching.value && !workspace.batch.data.value"
        message="Loading the latest research recommendations…"
      />
      <ErrorState
        v-else-if="workspace.batch.isError.value && !workspace.batch.data.value"
        message="The latest recommendations could not be loaded."
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
          v-if="!workspace.batch.data.value.items.length"
          message="This assessment returned no recommendations. Review your strategy or try again when new source evidence is available."
        />
        <RecommendationList
          v-else
          :key="`${workspace.identity.value}:${workspace.batch.data.value.id}`"
          :inert="workspace.generating.value || workspace.batch.isFetching.value"
          :batch="workspace.batch.data.value"
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
