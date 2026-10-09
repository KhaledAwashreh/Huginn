<script setup lang="ts">
import Button from 'primevue/button';
import { RouterLink } from 'vue-router';
import type { components } from '../../../api/generated/schema';
import { formatPipelineTime } from '../formatting/formatPipelineTime';

type EventEntry = components['schemas']['EventEntryResponse'];
defineProps<{
  invocationId: string;
  entries: EventEntry[];
  hasMore: boolean;
  loading: boolean;
  error: boolean;
  lastUpdatedAt: number;
  loadNext: () => void;
  retry: () => void;
}>();
</script>

<template>
  <section aria-labelledby="event-log-title" class="event-log">
    <h2 id="event-log-title">Event history</h2>
    <p class="muted">
      Events are shown in sequence order. Older pages remain available when more than 100 events
      exist.
    </p>
    <p v-if="error" role="alert">
      Events could not be refreshed.<template v-if="lastUpdatedAt">
        Showing events last received at {{ new Date(lastUpdatedAt).toLocaleString() }}.</template
      >
    </p>
    <ol>
      <li v-for="event in entries" :key="event.sequence">
        <time :datetime="event.occurred_at" :title="event.occurred_at">{{
          formatPipelineTime(event.occurred_at)
        }}</time>
        <strong>{{ event.kind.replaceAll('_', ' ') }}</strong>
        <span v-if="event.stage_name"
          >Stage:
          <RouterLink
            :to="{
              name: 'admin-pipeline-invocation',
              params: { id: invocationId },
              query: {
                stage: event.stage_name.startsWith('gold.')
                  ? 'gold'
                  : event.stage_name.startsWith('silver.')
                    ? 'silver'
                    : undefined,
              },
            }"
            >{{ event.stage_name }}</RouterLink
          ></span
        >
        <span v-if="event.source_name"
          >Source:
          <RouterLink
            :to="{
              name: 'admin-pipeline-invocation',
              params: { id: invocationId },
              query: { stage: 'bronze' },
            }"
            >{{ event.source_name }}</RouterLink
          ></span
        >
        <p>{{ event.safe_message ?? event.safe_code ?? 'No safe message supplied.' }}</p>
      </li>
    </ol>
    <p v-if="!entries.length && !loading" class="muted">No events have been recorded.</p>
    <div class="event-actions">
      <Button
        v-if="hasMore"
        label="Load next events"
        severity="secondary"
        :disabled="loading"
        @click="loadNext"
      />
      <Button
        v-if="error"
        label="Retry events"
        severity="secondary"
        :disabled="loading"
        @click="retry"
      />
      <span v-if="loading" role="status">Refreshing events…</span>
    </div>
  </section>
</template>

<style scoped>
.event-log {
  margin-top: var(--space-6);
}
h2 {
  margin-bottom: var(--space-2);
}
.muted {
  color: var(--color-text-muted);
}
ol {
  display: grid;
  gap: var(--space-3);
  padding-left: 1.5rem;
}
li {
  padding-left: var(--space-1);
  overflow-wrap: anywhere;
}
li > * {
  margin-right: var(--space-2);
}
li p {
  margin: var(--space-1) 0 0;
  white-space: pre-wrap;
}
.event-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
}
</style>
