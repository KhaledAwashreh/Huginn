<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import type { MatchmakingTargetState, UserResult } from '../api/listUserResults';
import SkippedStrategyList from './SkippedStrategyList.vue';
const props = defineProps<{
  runId: string;
  items: UserResult[];
  hasMore: boolean;
  offset: number;
  pageSize: number;
  state: MatchmakingTargetState | undefined;
}>();
const emit = defineEmits<{
  (event: 'update:offset', value: number): void;
  (event: 'update:state', value: MatchmakingTargetState | undefined): void;
}>();
const expanded = ref<string>();
const stateOptions: Array<MatchmakingTargetState | 'all'> = [
  'all',
  'pending',
  'running',
  'succeeded',
  'disabled_user',
  'user_not_found',
  'failed',
  'commit_outcome_unknown',
  'not_executed',
];
const selectedState = computed<MatchmakingTargetState | 'all'>({
  get: () => props.state ?? 'all',
  set: (value) => {
    emit('update:state', value === 'all' ? undefined : value);
    emit('update:offset', 0);
  },
});
function count(value: number | null | undefined) {
  return value == null ? 'Unknown' : value;
}
</script>

<template>
  <section class="results">
    <div class="filters">
      <h2>User outcomes</h2>
      <label
        >Filter state
        <select v-model="selectedState">
          <option v-for="option in stateOptions" :key="option" :value="option">
            {{ option === 'all' ? 'All states' : option.replaceAll('_', ' ') }}
          </option>
        </select></label
      >
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Target user</th>
            <th>Outcome</th>
            <th>Strategies evaluated / skipped</th>
            <th>Matches created / existing</th>
            <th>Reason</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in items" :key="item.user_id"
            ><tr>
              <td>
                <code>{{ item.user_id }}</code>
              </td>
              <td>{{ item.state.replaceAll('_', ' ') }}</td>
              <td>{{ count(item.strategies_evaluated) }} / {{ count(item.strategies_skipped) }}</td>
              <td>
                {{ count(item.created_matches_count) }} /
                {{ count(item.existing_matches_skipped_count) }}
              </td>
              <td>{{ item.safe_reason || '—' }}</td>
              <td>
                <Button
                  type="button"
                  severity="secondary"
                  :aria-expanded="expanded === item.user_id"
                  :aria-label="`${expanded === item.user_id ? 'Hide' : 'Show'} details for user ${item.user_id}`"
                  @click="expanded = expanded === item.user_id ? undefined : item.user_id"
                >
                  {{ expanded === item.user_id ? 'Hide' : 'Show' }} details
                </Button>
              </td>
            </tr>
            <tr v-if="expanded === item.user_id">
              <td colspan="6">
                <p>
                  Unique candidates: {{ count(item.unique_candidates_count) }} · Started:
                  {{ item.started_at || 'Not started' }} · Finished:
                  {{ item.finished_at || 'Not finished' }}
                </p>
                <SkippedStrategyList
                  v-if="item.strategies_skipped"
                  :label="`Skipped strategies for user ${item.user_id}`"
                  :run-id="runId"
                  :user-id="item.user_id"
                />
                <p v-else-if="item.strategies_skipped === 0">
                  No skipped strategies were recorded for this user.
                </p>
                <p v-else>Skipped-strategy count is unknown.</p>
              </td>
            </tr></template
          >
          <tr v-if="!items.length">
            <td colspan="6">No user outcomes on this page.</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pager">
      <span
        >{{ items.length }} outcomes on this page · users {{ offset + 1 }}–{{
          offset + items.length
        }}</span
      ><Button
        type="button"
        label="Previous outcomes"
        severity="secondary"
        :disabled="offset === 0"
        @click="emit('update:offset', Math.max(0, offset - pageSize))"
      /><Button
        type="button"
        label="Next outcomes"
        severity="secondary"
        :disabled="!hasMore"
        @click="emit('update:offset', offset + pageSize)"
      />
    </div>
  </section>
</template>

<style scoped>
.filters,
.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-3);
}
.table-wrap {
  overflow-x: auto;
}
table {
  border-collapse: collapse;
  width: 100%;
  min-width: 52rem;
}
th,
td {
  text-align: left;
  vertical-align: top;
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
}
td code {
  overflow-wrap: anywhere;
}
</style>
