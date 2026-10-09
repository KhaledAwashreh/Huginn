<script setup lang="ts">
import Button from 'primevue/button';
import type { components } from '../../../api/generated/schema';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';

type Company = components['schemas']['InvocationCompanyResultResponse'];
defineProps<{
  items: Company[];
  trackingState: 'tracked' | 'unknown_legacy' | undefined;
  totalCount: number | undefined;
  offset: number;
  pageSize: number;
  hasMore: boolean;
  loading: boolean;
  error: boolean;
  lastUpdatedAt: number;
  previousPage: () => void;
  nextPage: () => void;
  retry: () => void;
}>();
</script>

<template>
  <section class="company-results" aria-labelledby="company-results-title">
    <h2 id="company-results-title">Companies written by this run</h2>
    <p>
      These companies were processed or written by this run. They are not necessarily new or
      changed, and their current fields may reflect later edits.
    </p>
    <LoadingState v-if="loading && !items.length" message="Loading this run’s company results…" />
    <EmptyState
      v-else-if="trackingState === 'unknown_legacy'"
      message="Company membership is unavailable for this legacy invocation."
    />
    <EmptyState
      v-else-if="!loading && !error && !items.length"
      message="This run has no attributed company writes."
    />
    <ErrorState
      v-if="error"
      :message="`This company-results page could not be refreshed.${lastUpdatedAt ? ` The last known page was received at ${new Date(lastUpdatedAt).toLocaleString()}.` : ''}`"
    >
      <Button label="Retry results" severity="secondary" :disabled="loading" @click="retry" />
    </ErrorState>
    <p v-if="trackingState === 'tracked' && totalCount !== undefined" class="result-count">
      {{ totalCount }} companies written by this run
    </p>
    <div
      v-if="items.length"
      class="results-table-wrap"
      tabindex="0"
      role="region"
      aria-label="Company results"
    >
      <table class="results-table">
        <caption>
          Current fields for companies explicitly attributed to this invocation
        </caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Domain</th>
            <th scope="col">Business sector</th>
            <th scope="col">Country</th>
            <th scope="col">Scale</th>
            <th scope="col">Status</th>
            <th scope="col">Company ID</th>
            <th scope="col">Writing stage job ID</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="company in items" :key="company.id">
            <th scope="row">{{ company.name }}</th>
            <td>{{ company.domain ?? 'Unknown' }}</td>
            <td>
              {{
                Array.isArray(company.business_sector)
                  ? company.business_sector.join(', ')
                  : (company.business_sector ?? 'Unknown')
              }}
            </td>
            <td>{{ company.country ?? 'Unknown' }}</td>
            <td>{{ company.company_scale ?? 'Unknown' }}</td>
            <td>{{ company.company_status ?? 'Unknown' }}</td>
            <td>
              <code>{{ company.id }}</code>
            </td>
            <td>
              <code>{{ company.stage_job_run_id }}</code>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="trackingState === 'tracked' && totalCount" class="pagination">
      <Button
        label="Previous results"
        severity="secondary"
        :disabled="offset === 0 || loading"
        @click="previousPage"
      />
      <span
        >Results {{ offset + 1 }}–{{ Math.min(offset + pageSize, totalCount) }} of
        {{ totalCount }}</span
      >
      <Button
        label="Next results"
        severity="secondary"
        :disabled="!hasMore || loading"
        @click="nextPage"
      />
    </div>
  </section>
</template>

<style scoped>
.company-results {
  margin-top: var(--space-6);
}
h2 {
  margin-bottom: var(--space-2);
}
.results-table-wrap {
  overflow-x: auto;
}
.results-table {
  width: 100%;
  min-width: 1050px;
  border-collapse: collapse;
}
caption {
  padding: var(--space-2);
  text-align: left;
  color: var(--color-text-muted);
}
th,
td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}
td,
th {
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
  margin-top: var(--space-3);
}
.result-count {
  font-weight: 600;
}
</style>
