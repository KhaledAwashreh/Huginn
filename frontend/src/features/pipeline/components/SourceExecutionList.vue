<script setup lang="ts">
import type { components } from '../../../api/generated/schema';
import StatusLabel from '../../../shared/ui/StatusLabel.vue';
import { formatPipelineMetric } from '../formatting/formatPipelineMetric';
import { formatPipelineTime } from '../formatting/formatPipelineTime';

type SourceExecution = components['schemas']['SourceExecutionResponse'];
defineProps<{ sources: SourceExecution[]; parentJobRunId: string | null }>();
</script>

<template>
  <section
    class="source-list"
    :aria-label="`Source jobs for ${parentJobRunId ?? 'unmatched parent'}`"
  >
    <h4>Source jobs</h4>
    <p v-if="!parentJobRunId" class="muted">No parent job ID was recorded for this stage.</p>
    <ul v-else-if="!sources.some((source) => source.parent_job_run_id === parentJobRunId)">
      <li>No child source jobs recorded for this parent.</li>
    </ul>
    <ul v-else>
      <li
        v-for="source in sources.filter((item) => item.parent_job_run_id === parentJobRunId)"
        :key="source.job_run_id"
      >
        <div class="source-heading">
          <strong>{{ source.name }}</strong
          ><StatusLabel :status="source.state" />
        </div>
        <p>
          <code>{{ source.job_run_id }}</code>
        </p>
        <p>
          Started
          <time
            :datetime="source.started_at ?? undefined"
            :title="source.started_at ?? undefined"
            >{{ formatPipelineTime(source.started_at) }}</time
          >
          · finished
          <time
            :datetime="source.finished_at ?? undefined"
            :title="source.finished_at ?? undefined"
            >{{ formatPipelineTime(source.finished_at) }}</time
          >
        </p>
        <p v-if="source.safe_error_code">Safe error: {{ source.safe_error_code }}</p>
        <dl v-if="source.metrics.length" class="metrics">
          <div v-for="metric in source.metrics" :key="metric.kind">
            <dt>{{ formatPipelineMetric(metric).label }}</dt>
            <dd>{{ formatPipelineMetric(metric).value }}</dd>
          </div>
        </dl>
        <p v-else class="muted">No metrics recorded</p>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.source-list {
  margin-top: var(--space-3);
  padding: var(--space-3);
  background: var(--color-surface-muted);
  border-radius: var(--radius-control);
}
h4 {
  margin: 0 0 var(--space-2);
}
ul {
  display: grid;
  gap: var(--space-3);
  padding-left: 1.25rem;
}
li {
  overflow-wrap: anywhere;
}
.source-heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}
p {
  margin: var(--space-1) 0;
}
.metrics {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin: var(--space-2) 0 0;
}
dt,
.muted {
  color: var(--color-text-muted);
}
dd {
  margin: 0;
}
</style>
