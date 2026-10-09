<script setup lang="ts">
import { computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Button from 'primevue/button';
import Select from 'primevue/select';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import StatusLabel from '../../../shared/ui/StatusLabel.vue';
import RunPipelineAction from '../components/RunPipelineAction.vue';
import { useSession } from '../../session/composables/useSession';
import { usePipelineHistory } from '../composables/usePipelineHistory';
import { formatPipelineDuration, formatPipelineTime } from '../formatting/formatPipelineTime';
import { pipelineQueryLocation, validatePipelineQuery } from '../navigation/validatePipelineQuery';

const route = useRoute();
const router = useRouter();
const session = useSession();
const history = usePipelineHistory();
const query = computed(() => validatePipelineQuery(route.query));
const historyReady = computed(
  () =>
    history.history.data.value !== undefined &&
    !history.history.isError.value &&
    history.state.value === undefined &&
    history.offset.value === 0,
);
const filters = [
  { label: 'All states', value: undefined },
  { label: 'Queued', value: 'queued' },
  { label: 'Running', value: 'running' },
  { label: 'Succeeded', value: 'succeeded' },
  { label: 'Failed', value: 'failed' },
  { label: 'Interrupted', value: 'interrupted' },
];

watch(
  query,
  (next) => {
    history.setState(next.state);
    history.offset.value = next.offset;

    const canonicalQuery = {
      ...(next.state ? { state: next.state } : {}),
      ...(next.offset > 0 ? { offset: String(next.offset) } : {}),
    };
    if (JSON.stringify(route.query) !== JSON.stringify(canonicalQuery))
      void router.replace({ query: canonicalQuery });
  },
  { immediate: true },
);

watch(history.state, (state) => {
  if (state !== query.value.state)
    void router.replace({
      query: pipelineQueryLocation({
        stage: query.value.stage,
        ...(state ? { state } : {}),
        offset: 0,
      }),
    });
});

function setOffset(offset: number): void {
  void router.push({ query: pipelineQueryLocation({ ...query.value, offset }) });
}

function refresh(): void {
  void history.history.refetch();
}
</script>

<template>
  <PageHeader
    title="Data collection"
    description="Pull data starts the existing HN, YC, and EU-Startups collection pipeline."
  >
    <RunPipelineAction v-if="session.isAdministrator.value" :can-trigger="historyReady" />
  </PageHeader>
  <section v-if="!session.isAdministrator.value" class="forbidden" role="alert">
    <h2>Administrator access required</h2>
    <p>Your session cannot view collection history.</p>
  </section>
  <template v-else>
    <div class="history-filter">
      <label for="invocation-state">Filter by state</label
      ><Select
        input-id="invocation-state"
        :model-value="history.state.value"
        :options="filters"
        option-label="label"
        option-value="value"
        @update:model-value="history.setState"
      />
    </div>
    <LoadingState v-if="history.history.isPending.value" message="Loading collection history…" />
    <ErrorState
      v-else-if="history.history.isError.value && !history.history.data.value"
      :message="
        history.history.error.value instanceof Error
          ? history.history.error.value.message
          : 'Collection history could not be loaded.'
      "
      ><Button
        label="Refresh history"
        :disabled="history.history.isFetching.value"
        @click="refresh"
    /></ErrorState>
    <template v-else-if="history.history.data.value">
      <p v-if="history.history.isError.value" class="refresh-error" role="alert">
        History refresh failed. Showing the page last received at
        {{ new Date(history.history.dataUpdatedAt.value).toLocaleString() }}.
      </p>
      <p v-if="history.history.isFetching.value" class="refreshing" role="status">
        Refreshing active runs…
      </p>
      <EmptyState
        v-if="!history.history.data.value.items.length"
        message="No collection runs match this filter."
      />
      <div v-else class="history-table-wrap">
        <table class="history-table">
          <caption class="visually-hidden">
            Collection invocation history
          </caption>
          <thead>
            <tr>
              <th scope="col">Requested</th>
              <th scope="col">Invocation ID</th>
              <th scope="col">State</th>
              <th scope="col">Requester account</th>
              <th scope="col">Duration</th>
              <th scope="col">Details</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in history.history.data.value.items" :key="item.id">
              <td>
                <time :datetime="item.requested_at" :title="item.requested_at">{{
                  formatPipelineTime(item.requested_at)
                }}</time>
              </td>
              <td>
                <code>{{ item.id }}</code>
              </td>
              <td><StatusLabel :status="item.state" /></td>
              <td>
                <code>{{ item.requester_account_id }}</code>
              </td>
              <td>{{ formatPipelineDuration(item.started_at, item.finished_at) }}</td>
              <td>
                <RouterLink :to="`/admin/pipeline/invocations/${item.id}`"
                  >View invocation</RouterLink
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pagination">
        <Button
          label="Previous page"
          severity="secondary"
          :disabled="history.offset.value === 0 || history.history.isFetching.value"
          @click="setOffset(Math.max(0, history.offset.value - history.pageSize))"
        /><span>Page {{ Math.floor(history.offset.value / history.pageSize) + 1 }}</span
        ><Button
          label="Next page"
          severity="secondary"
          :disabled="!history.history.data.value.has_more || history.history.isFetching.value"
          @click="setOffset(history.offset.value + history.pageSize)"
        /><Button
          label="Refresh history"
          severity="secondary"
          :disabled="history.history.isFetching.value"
          @click="refresh"
        />
      </div>
    </template>
  </template>
</template>

<style scoped>
.history-filter {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.history-table-wrap {
  overflow-x: auto;
}
.history-table {
  width: 100%;
  min-width: 850px;
  border-collapse: collapse;
}
th,
td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}
th {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
td {
  overflow-wrap: anywhere;
}
code {
  overflow-wrap: anywhere;
}
.pagination {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-top: var(--space-4);
}
.refreshing {
  color: var(--color-text-muted);
}
.forbidden {
  padding: var(--space-4);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-card);
}
</style>
