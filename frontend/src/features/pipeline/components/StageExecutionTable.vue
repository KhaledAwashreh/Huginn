<script setup lang="ts">
import type { components } from '../../../api/generated/schema';
import StatusLabel from '../../../shared/ui/StatusLabel.vue';
import SourceExecutionList from './SourceExecutionList.vue';
import { formatPipelineMetric } from '../formatting/formatPipelineMetric';
import { formatPipelineTime } from '../formatting/formatPipelineTime';

type StageExecution = components['schemas']['StageExecutionResponse'];
type SourceExecution = components['schemas']['SourceExecutionResponse'];
defineProps<{
  stages: StageExecution[];
  sources: SourceExecution[];
  group: 'source' | 'silver' | 'gold';
}>();

function stateCopy(stage: StageExecution): string {
  if (stage.state === 'skipped')
    return `Skipped${stage.skip_reason ? `: ${stage.skip_reason}` : ' because a dependency did not succeed.'}`;
  if (stage.state === 'interrupted')
    return 'Interrupted when execution stopped; this stage did not finish.';
  if (stage.state === 'not_executed') return 'Not executed after interruption.';
  return stage.safe_error_code ? `Safe error: ${stage.safe_error_code}` : '';
}
</script>

<template>
  <div class="stage-table-wrap" tabindex="0" role="region" aria-label="Stage execution results">
    <table class="stage-table">
      <caption class="visually-hidden">
        {{
          group
        }}
        pipeline stages
      </caption>
      <thead>
        <tr>
          <th scope="col">Stage</th>
          <th scope="col">State</th>
          <th scope="col">Dependencies</th>
          <th scope="col">Timing and metrics</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="stage in stages" :key="stage.name">
          <th scope="row">
            <span>{{ stage.name }}</span
            ><small v-if="stateCopy(stage)">{{ stateCopy(stage) }}</small>
          </th>
          <td>
            <StatusLabel :status="stage.state" /><progress
              v-if="stage.state === 'running' && group === 'source'"
              aria-label="Source work in progress"
            />
          </td>
          <td>{{ stage.dependencies.length ? stage.dependencies.join(', ') : 'None' }}</td>
          <td>
            <p :title="stage.started_at ?? undefined">
              Started {{ formatPipelineTime(stage.started_at) }}
            </p>
            <p :title="stage.finished_at ?? undefined">
              Finished {{ formatPipelineTime(stage.finished_at) }}
            </p>
            <dl v-if="stage.metrics.length" class="metrics">
              <div v-for="metric in stage.metrics" :key="metric.kind">
                <dt>{{ formatPipelineMetric(metric).label }}</dt>
                <dd>{{ formatPipelineMetric(metric).value }}</dd>
              </div>
            </dl>
            <p v-else class="muted">No metrics recorded</p>
            <SourceExecutionList
              v-if="group === 'source'"
              :sources="sources"
              :parent-job-run-id="stage.job_run_id ?? null"
            />
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="group === 'silver'" class="review-note">
      Manual review queueing is part of Silver. This console does not change review decisions.
    </p>
  </div>
</template>

<style scoped>
.stage-table-wrap {
  overflow-x: auto;
}
.stage-table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
}
th,
td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}
thead th {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
tbody th {
  max-width: 250px;
  overflow-wrap: anywhere;
}
small {
  display: block;
  margin-top: var(--space-1);
  color: var(--color-text-muted);
  font-weight: 400;
}
p {
  margin: var(--space-1) 0;
}
progress {
  display: block;
  width: 100%;
  margin-top: var(--space-2);
}
.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin: var(--space-2) 0;
}
.metrics dt,
.muted {
  color: var(--color-text-muted);
}
.metrics dd {
  margin: 0;
}
.review-note {
  padding: var(--space-3);
  border-left: 3px solid var(--color-border);
}
</style>
