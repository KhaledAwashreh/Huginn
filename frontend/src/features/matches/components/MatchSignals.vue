<script setup lang="ts">
import Button from 'primevue/button';
import { ApiError } from '../../../api/apiError';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import type { MatchSignalsPage } from '../api/listMatchSignals';
import { safeSourceUrl } from '../lib/externalCompanyUrl';

defineProps<{
  page: MatchSignalsPage | undefined;
  offset: number;
  pageSize: number;
  pending: boolean;
  fetching: boolean;
  failed: boolean;
  error: unknown;
}>();
const emit = defineEmits<{ previous: []; next: []; retry: [] }>();

function canRetry(error: unknown): boolean {
  return (
    !(error instanceof ApiError) ||
    error.status >= 500 ||
    error.status === 429 ||
    error.status === 408
  );
}
</script>

<template>
  <section class="signals" data-testid="match-signals" aria-labelledby="signals-heading">
    <div class="section-heading">
      <div>
        <h2 id="signals-heading">Current company signals</h2>
        <p>
          These are current signals for the company. They do not explain why this match was created.
        </p>
      </div>
      <span v-if="fetching && page" role="status">Refreshing signals…</span>
    </div>
    <LoadingState v-if="pending && !page" message="Loading current company signals…" />
    <ErrorState v-else-if="failed && !page" message="Current company signals could not be loaded.">
      <Button
        v-if="canRetry(error)"
        label="Retry signals"
        :disabled="fetching"
        @click="emit('retry')"
      />
    </ErrorState>
    <template v-else-if="page">
      <ErrorState v-if="failed" message="Signal refresh failed. Showing the last received page.">
        <Button
          v-if="canRetry(error)"
          label="Retry signals"
          :disabled="fetching"
          @click="emit('retry')"
        />
      </ErrorState>
      <EmptyState v-if="!page.items.length" message="No current company signals are available." />
      <ul v-else class="signal-list">
        <li v-for="signal in page.items" :key="signal.id" data-testid="signal-row">
          <div class="signal-title">
            <strong>{{ signal.signal_type }}</strong
            ><span>{{ signal.source }}</span>
          </div>
          <time :datetime="signal.occurred_at">{{
            new Date(signal.occurred_at).toLocaleString()
          }}</time>
          <p v-if="signal.description">{{ signal.description }}</p>
          <p v-if="signal.stage"><span>Stage:</span> {{ signal.stage }}</p>
          <a
            v-if="safeSourceUrl(signal.source_url)"
            :href="safeSourceUrl(signal.source_url) ?? undefined"
            target="_blank"
            rel="noopener noreferrer"
            >Open source</a
          >
          <span v-else-if="signal.source_url" class="source-text">{{ signal.source_url }}</span>
        </li>
      </ul>
      <nav class="pagination" aria-label="Signal pages">
        <Button
          label="Previous page"
          severity="secondary"
          :disabled="offset === 0 || fetching"
          @click="emit('previous')"
        />
        <span>Page {{ Math.floor(offset / pageSize) + 1 }}</span>
        <Button
          label="Next page"
          severity="secondary"
          :disabled="!page.has_more || fetching"
          @click="emit('next')"
        />
      </nav>
    </template>
  </section>
</template>

<style scoped>
.signals {
  display: grid;
  gap: var(--space-4);
}
.section-heading {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
}
h2 {
  margin: 0;
  font-size: 1.2rem;
}
.section-heading p {
  color: var(--color-text-muted);
  margin: var(--space-2) 0 0;
}
.signal-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--space-3);
}
.signal-list li {
  min-width: 0;
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  overflow-wrap: anywhere;
}
.signal-title {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
  flex-wrap: wrap;
}
.signal-title span,
time,
.source-text {
  color: var(--color-text-muted);
  font-size: 0.9rem;
}
time {
  display: block;
  margin-top: var(--space-1);
}
.signal-list p {
  margin: var(--space-3) 0;
  white-space: pre-wrap;
}
.signal-list a {
  color: var(--color-primary);
}
.pagination {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
</style>
