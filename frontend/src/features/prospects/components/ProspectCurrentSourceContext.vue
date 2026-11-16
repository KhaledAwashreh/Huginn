<script setup lang="ts">
import { safeSourceUrl } from '../../../shared/lib/externalCompanyUrl';
import type { ProspectView } from '../models/prospect';

defineProps<{ context: NonNullable<ProspectView['current_source_context']> }>();
function displayTime(value: string): string {
  return new Date(value).toLocaleString(undefined, { timeZone: 'UTC', timeZoneName: 'short' });
}
</script>

<template>
  <section class="current-sources" aria-label="Current guarded source context">
    <h3>Current source context</h3>
    <p>
      These sources describe the company now. Fit has not been reassessed; the original assessment
      and its evidence remain preserved below.
    </p>
    <p v-if="context.evidence_state === 'changed'">
      Current source evidence differs from the evidence saved with this prospect.
    </p>
    <p v-else-if="context.evidence_state === 'current'">
      The current source observations match the evidence saved with this prospect.
    </p>
    <p v-else-if="context.evidence_state === 'unavailable'">
      Current source evidence is unavailable. The saved assessment evidence remains readable below.
    </p>
    <p v-else>No source observations were retained with this prospect’s origins.</p>
    <article
      v-for="signal in context.signals"
      :key="signal.observation_id"
      :data-observation-id="signal.observation_id"
      class="current-source"
    >
      <h4>
        {{ signal.source.replaceAll('_', ' ') }} · {{ signal.evidence_kind.replaceAll('_', ' ') }}
      </h4>
      <p class="source-text">{{ signal.description || 'Source text unavailable.' }}</p>
      <a
        v-if="safeSourceUrl(signal.source_url)"
        :href="safeSourceUrl(signal.source_url) ?? undefined"
        target="_blank"
        rel="noopener noreferrer"
        >Open current source</a
      >
      <span v-else>Source link unavailable</span>
      <dl>
        <div>
          <dt>Source date</dt>
          <dd>
            <time v-if="signal.occurred_at" :datetime="signal.occurred_at">{{
              displayTime(signal.occurred_at)
            }}</time>
            <span v-else>Unknown</span>
          </dd>
        </div>
        <div>
          <dt>Observed</dt>
          <dd>
            <time :datetime="signal.observed_at">{{ displayTime(signal.observed_at) }}</time>
          </dd>
        </div>
        <div>
          <dt>Ingested</dt>
          <dd>
            <time :datetime="signal.ingested_at">{{ displayTime(signal.ingested_at) }}</time>
          </dd>
        </div>
      </dl>
    </article>
    <p v-if="context.has_more">Showing the first 50 current sources, ordered by source date.</p>
  </section>
</template>

<style scoped>
.current-sources,
.current-source {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
}
h3,
h4,
p {
  margin: 0;
}
.current-sources > p,
dt {
  color: var(--color-text-muted);
}
.current-source {
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-3);
}
.source-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
a {
  color: var(--color-primary);
  overflow-wrap: anywhere;
}
dl {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin: 0;
}
dd {
  margin: 0;
}
</style>
