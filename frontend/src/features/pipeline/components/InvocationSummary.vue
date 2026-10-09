<script setup lang="ts">
import { computed } from 'vue';
import type { components } from '../../../api/generated/schema';
import StatusLabel from '../../../shared/ui/StatusLabel.vue';
import { formatPipelineTime } from '../formatting/formatPipelineTime';

type Invocation = components['schemas']['InvocationDetailResponse'];
const props = defineProps<{ invocation: Invocation }>();
const finished = computed(
  () =>
    props.invocation.stages.filter((stage) =>
      ['succeeded', 'failed', 'skipped'].includes(stage.state),
    ).length,
);
const failed = computed(
  () => props.invocation.stages.filter((stage) => stage.state === 'failed').length,
);
const skipped = computed(
  () => props.invocation.stages.filter((stage) => stage.state === 'skipped').length,
);
const stale = computed(
  () => props.invocation.state === 'running' && props.invocation.tracking_state === 'stale',
);
</script>

<template>
  <section class="invocation-summary" aria-label="Invocation summary">
    <div class="summary-heading">
      <StatusLabel :status="invocation.state" /><span>{{ finished }} of 9 stages finished</span>
    </div>
    <dl>
      <div>
        <dt>Invocation ID</dt>
        <dd>
          <code>{{ invocation.id }}</code>
        </dd>
      </div>
      <div>
        <dt>Requester account</dt>
        <dd>
          <code>{{ invocation.requester_account_id }}</code>
        </dd>
      </div>
      <div>
        <dt>Requested</dt>
        <dd>
          <time :datetime="invocation.requested_at" :title="invocation.requested_at">{{
            formatPipelineTime(invocation.requested_at)
          }}</time>
        </dd>
      </div>
      <div>
        <dt>Started</dt>
        <dd>
          <time
            v-if="invocation.started_at"
            :datetime="invocation.started_at"
            :title="invocation.started_at"
            >{{ formatPipelineTime(invocation.started_at) }}</time
          ><span v-else>Not started</span>
        </dd>
      </div>
      <div>
        <dt>Finished</dt>
        <dd>
          <time
            v-if="invocation.finished_at"
            :datetime="invocation.finished_at"
            :title="invocation.finished_at"
            >{{ formatPipelineTime(invocation.finished_at) }}</time
          ><span v-else>Not finished</span>
        </dd>
      </div>
      <div>
        <dt>Last tracker update</dt>
        <dd>
          <time
            v-if="invocation.heartbeat_at"
            :datetime="invocation.heartbeat_at"
            :title="invocation.heartbeat_at"
            >{{ formatPipelineTime(invocation.heartbeat_at) }}</time
          ><span v-else>Not recorded</span>
        </dd>
      </div>
      <div>
        <dt>Failed stages</dt>
        <dd>{{ failed }}</dd>
      </div>
      <div>
        <dt>Dependency skips</dt>
        <dd>{{ skipped }}</dd>
      </div>
    </dl>
    <p v-if="invocation.safe_error_code" role="status">
      Safe run error: {{ invocation.safe_error_code }}
    </p>
    <div v-if="stale" class="stale-notice" role="status">
      <strong>Tracking is stale.</strong> The last heartbeat is over 60 seconds old. This run
      remains active until a trusted operator verifies and reconciles the executor.
    </div>
  </section>
</template>

<style scoped>
.invocation-summary {
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
.summary-heading {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-weight: 600;
}
dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3) var(--space-5);
  margin: var(--space-4) 0 0;
}
dt {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
dd {
  margin: var(--space-1) 0 0;
  overflow-wrap: anywhere;
}
.stale-notice {
  margin-top: var(--space-4);
  padding: var(--space-3);
  border-left: 4px solid var(--color-warning-border);
  background: var(--color-warning-surface);
}
code {
  overflow-wrap: anywhere;
}
</style>
