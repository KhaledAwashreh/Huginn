<script setup lang="ts">
import { computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Button from 'primevue/button';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import InvocationSummary from '../components/InvocationSummary.vue';
import StageExecutionTable from '../components/StageExecutionTable.vue';
import InvocationEventLog from '../components/InvocationEventLog.vue';
import InvocationCompanyResults from '../components/InvocationCompanyResults.vue';
import { useSession } from '../../session/composables/useSession';
import { usePipelineInvocation } from '../composables/usePipelineInvocation';
import { useInvocationEvents } from '../composables/useInvocationEvents';
import { useInvocationCompanies } from '../composables/useInvocationCompanies';
import { validateInvocationId, validatePipelineQuery } from '../navigation/validatePipelineQuery';

const route = useRoute();
const router = useRouter();
const session = useSession();
const invocationId = computed(() => String(route.params.id ?? ''));
const validId = computed(() => validateInvocationId(invocationId.value));
const routeQuery = computed(() => validatePipelineQuery(route.query));
const selectedStage = computed(() => routeQuery.value.stage);
const detail = usePipelineInvocation(() => (validId.value ? invocationId.value : ''));
const eventLog = useInvocationEvents(
  () => (validId.value ? invocationId.value : ''),
  () => detail.invocation.data.value?.state,
);
const companyResults = useInvocationCompanies(
  () => (validId.value ? invocationId.value : ''),
  () => detail.invocation.data.value?.state,
);
const stageTabs: { value: 'bronze' | 'silver' | 'gold'; label: string }[] = [
  { value: 'bronze', label: 'Source / Bronze' },
  { value: 'silver', label: 'Silver' },
  { value: 'gold', label: 'Gold' },
];

function selectStage(stage: 'bronze' | 'silver' | 'gold'): void {
  void router.replace({ query: { ...route.query, stage: stage === 'bronze' ? undefined : stage } });
}

function moveStageTab(event: KeyboardEvent): void {
  const buttons = Array.from(
    (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="tab"]'),
  );
  const currentIndex = buttons.indexOf(event.target as HTMLButtonElement);
  if (currentIndex < 0) return;
  let nextIndex = currentIndex;
  if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % stageTabs.length;
  else if (event.key === 'ArrowLeft')
    nextIndex = (currentIndex + stageTabs.length - 1) % stageTabs.length;
  else if (event.key === 'Home') nextIndex = 0;
  else if (event.key === 'End') nextIndex = stageTabs.length - 1;
  else return;
  event.preventDefault();
  buttons[nextIndex]?.focus();
  const tab = stageTabs[nextIndex];
  if (tab) selectStage(tab.value);
}

watch(
  routeQuery,
  (next) => {
    const rawStage = route.query.stage;
    const expectedStage = next.stage === 'bronze' ? undefined : next.stage;
    if (rawStage !== expectedStage)
      void router.replace({ query: { ...route.query, stage: expectedStage } });
  },
  { immediate: true },
);

const stages = computed(() => {
  const group = selectedStage.value === 'bronze' ? 'source' : selectedStage.value;
  return (detail.invocation.data.value?.stages ?? [])
    .filter((stage) => {
      if (group === 'source') return stage.name.startsWith('ingestion');
      return stage.name.startsWith(`${group}.`);
    })
    .sort((left, right) => left.order - right.order);
});

function retryDetails(): void {
  void detail.invocation.refetch();
}
</script>

<template>
  <PageHeader
    title="Collection invocation"
    description="Inspect the saved execution plan, observed progress, and events."
  >
    <RouterLink to="/admin/pipeline">Back to history</RouterLink>
  </PageHeader>
  <section v-if="!session.isAdministrator.value" class="forbidden" role="alert">
    <h2>Administrator access required</h2>
    <p>Your session cannot view this invocation.</p>
  </section>
  <ErrorState v-else-if="!validId" message="This invocation link does not contain a valid ID." />
  <LoadingState
    v-else-if="detail.invocation.isPending.value"
    message="Loading invocation details…"
  />
  <ErrorState
    v-else-if="detail.invocation.isError.value && !detail.invocation.data.value"
    :message="
      detail.invocation.error.value instanceof Error
        ? detail.invocation.error.value.message
        : 'Invocation details could not be loaded.'
    "
    ><Button
      label="Retry details"
      :disabled="detail.invocation.isFetching.value"
      @click="retryDetails"
  /></ErrorState>
  <template v-else-if="detail.invocation.data.value">
    <p v-if="detail.invocation.isFetching.value" class="freshness" role="status">
      Refreshing the last known invocation state…
    </p>
    <p v-if="detail.invocation.isError.value" class="freshness-error" role="alert">
      Refresh failed. The last known invocation state from
      {{ new Date(detail.invocation.dataUpdatedAt.value).toLocaleString() }} remains visible.
    </p>
    <InvocationSummary :invocation="detail.invocation.data.value" />
    <nav class="stage-tabs" aria-label="Pipeline stages" role="tablist" @keydown="moveStageTab">
      <button
        v-for="tab in stageTabs"
        :id="`stage-tab-${tab.value}`"
        :key="tab.value"
        type="button"
        role="tab"
        aria-controls="stage-panel"
        :aria-selected="selectedStage === tab.value"
        :tabindex="selectedStage === tab.value ? 0 : -1"
        @click="selectStage(tab.value)"
      >
        {{ tab.label }}
      </button>
    </nav>
    <section
      id="stage-panel"
      role="tabpanel"
      tabindex="0"
      :aria-labelledby="`stage-tab-${selectedStage}`"
    >
      <StageExecutionTable
        :stages="stages"
        :sources="detail.invocation.data.value.sources"
        :group="selectedStage === 'bronze' ? 'source' : selectedStage"
      />
    </section>
    <InvocationCompanyResults
      :items="companyResults.companies.data.value?.items ?? []"
      :tracking-state="companyResults.companies.data.value?.tracking_state"
      :total-count="companyResults.companies.data.value?.total_count"
      :offset="companyResults.offset.value"
      :page-size="companyResults.pageSize"
      :has-more="companyResults.companies.data.value?.has_more ?? false"
      :loading="companyResults.companies.isFetching.value"
      :error="companyResults.companies.isError.value"
      :last-updated-at="companyResults.companies.dataUpdatedAt.value"
      :previous-page="companyResults.previousPage"
      :next-page="companyResults.nextPage"
      :retry="() => companyResults.companies.refetch()"
    />
    <InvocationEventLog
      :invocation-id="invocationId"
      :entries="eventLog.entries.value"
      :has-more="eventLog.page.data.value?.has_more ?? false"
      :loading="eventLog.page.isFetching.value"
      :error="eventLog.page.isError.value"
      :last-updated-at="eventLog.page.dataUpdatedAt.value"
      :load-next="eventLog.loadNext"
      :retry="() => eventLog.page.refetch()"
    />
  </template>
</template>

<style scoped>
.forbidden {
  padding: var(--space-4);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-card);
}
.freshness {
  color: var(--color-text-muted);
}
.freshness-error {
  color: var(--color-danger-text);
}
.stage-tabs {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-block: var(--space-5) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}
.stage-tabs button {
  min-height: 44px;
  padding: var(--space-2) var(--space-4);
  border: 0;
  border-bottom: 3px solid transparent;
  background: transparent;
  color: var(--color-text-muted);
  font: inherit;
  cursor: pointer;
}
.stage-tabs button[aria-selected='true'] {
  border-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 650;
}
.stage-tabs button:focus-visible {
  outline: 3px solid var(--color-primary);
  outline-offset: 2px;
}
</style>
