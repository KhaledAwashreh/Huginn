<script setup lang="ts">
import { computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Button from 'primevue/button';
import Select from 'primevue/select';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import StatusLabel from '../../../shared/ui/StatusLabel.vue';
import { useSession } from '../../session/composables/useSession';
import { useMatchmakingHistory } from '../composables/useMatchmakingHistory';
import { validateMatchmakingQuery } from '../navigation/validateMatchmakingQuery';
import MatchmakingTriggerForm from '../components/MatchmakingTriggerForm.vue';
const route = useRoute();
const router = useRouter();
const session = useSession();
const history = useMatchmakingHistory();
const query = computed(() => validateMatchmakingQuery(route.query));
const filters = [
  { label: 'All states', value: undefined },
  { label: 'Queued', value: 'queued' },
  { label: 'Running', value: 'running' },
  { label: 'Succeeded', value: 'succeeded' },
  { label: 'Completed with errors', value: 'completed_with_errors' },
  { label: 'Interrupted', value: 'interrupted' },
];
watch(
  query,
  (next) => {
    history.setState(next.state);
    history.offset.value = next.offset;
    const normalized = {
      ...(next.state ? { state: next.state } : {}),
      ...(next.offset ? { offset: String(next.offset) } : {}),
    };
    if (JSON.stringify(route.query) !== JSON.stringify(normalized))
      void router.replace({ query: normalized });
  },
  { immediate: true },
);
function setOffset(offset: number) {
  void router.push({
    query: {
      ...(history.state.value ? { state: history.state.value } : {}),
      ...(offset ? { offset: String(offset) } : {}),
    },
  });
}
function setState(state: string | undefined) {
  void router.push({ query: { ...(state ? { state } : {}) } });
}
</script>

<template>
  <PageHeader
    title="Matchmaking"
    description="Review administrator-triggered matcher runs and their acknowledged user outcomes."
  />
  <section v-if="!session.isAdministrator.value" class="forbidden" role="alert">
    <h2>Administrator access required</h2>
    <p>Your session cannot view matchmaking history.</p>
  </section>
  <template v-else>
    <MatchmakingTriggerForm />
    <section class="history">
      <div class="filter">
        <h2>Run history</h2>
        <label for="matchmaking-state">Filter state</label
        ><Select
          input-id="matchmaking-state"
          :model-value="history.state.value"
          :options="filters"
          option-label="label"
          option-value="value"
          @update:model-value="setState"
        />
      </div>
      <LoadingState v-if="history.history.isPending.value" message="Loading matchmaking history…" />
      <ErrorState
        v-else-if="history.history.isError.value && !history.history.data.value"
        message="Matchmaking history could not be loaded."
        ><Button
          label="Refresh history"
          :disabled="history.history.isFetching.value"
          @click="history.history.refetch()"
      /></ErrorState>
      <template v-else-if="history.history.data.value">
        <p v-if="history.history.isError.value" role="alert">
          Refresh failed. Showing the last received history page.
        </p>
        <p v-if="history.history.isFetching.value" role="status">Refreshing active runs…</p>
        <EmptyState
          v-if="!history.history.data.value.items.length"
          message="No matchmaking runs match this filter."
        />
        <div v-else class="table-wrap">
          <table>
            <caption class="sr-only">
              Matchmaking run history
            </caption>
            <thead>
              <tr>
                <th>Requested</th>
                <th>Run ID</th>
                <th>State</th>
                <th>Requester account</th>
                <th>Users processed</th>
                <th>Window</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in history.history.data.value.items" :key="run.id">
                <td>
                  <time :datetime="run.requested_at">{{
                    new Date(run.requested_at).toLocaleString()
                  }}</time>
                </td>
                <td>
                  <code>{{ run.id }}</code>
                </td>
                <td><StatusLabel :status="run.state" /></td>
                <td>
                  <code>{{ run.requester_account_id }}</code>
                </td>
                <td>{{ run.settled_target_count }} / {{ run.target_count }} processed</td>
                <td>
                  {{ new Date(run.cutoff).toLocaleDateString() }} –
                  {{ new Date(run.as_of).toLocaleDateString() }}
                </td>
                <td>
                  <RouterLink :to="{ name: 'admin-matchmaking-run', params: { id: run.id } }"
                    >View run</RouterLink
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
          />
        </div>
      </template>
    </section>
  </template>
</template>

<style scoped>
.history {
  margin-top: 2rem;
}
.filter,
.pagination {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.filter h2 {
  margin-right: auto;
}
.table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  min-width: 56rem;
  border-collapse: collapse;
}
th,
td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}
td,
code {
  overflow-wrap: anywhere;
}
.pagination {
  margin-top: var(--space-4);
}
.forbidden {
  padding: var(--space-4);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-card);
}
.sr-only {
  position: absolute;
  clip: rect(0, 0, 0, 0);
}
</style>
