<script setup lang="ts">
import type { MatchmakingRunDetail } from '../api/getMatchmakingRun';
defineProps<{ run: MatchmakingRunDetail }>();
</script>

<template>
  <section class="progress-card" aria-label="Matchmaking run progress">
    <div class="headline">
      <strong>{{ run.settled_target_count }} / {{ run.target_count }} users processed</strong
      ><span>{{ run.state.replaceAll('_', ' ') }}</span>
    </div>
    <progress
      :max="Math.max(run.target_count, 1)"
      :value="run.settled_target_count"
      :aria-label="`${run.settled_target_count} of ${run.target_count} users processed`"
      :aria-valuetext="`${run.settled_target_count} of ${run.target_count} users processed`"
    >
      {{ run.settled_target_count }} of {{ run.target_count }}
    </progress>
    <p v-if="run.current_user_id" role="status">
      Matcher is currently evaluating user <code>{{ run.current_user_id }}</code
      >. Per-user evaluation has no estimated completion percentage.
    </p>
    <p>
      Processed users can have successful, skipped, failed, or unknown outcomes. Processed does not
      mean matched.
    </p>
    <dl>
      <div>
        <dt>Successful users</dt>
        <dd>{{ run.succeeded_count }}</dd>
      </div>
      <div>
        <dt>Skipped users</dt>
        <dd>{{ run.skipped_count }}</dd>
      </div>
      <div>
        <dt>Failed users</dt>
        <dd>{{ run.failed_count }}</dd>
      </div>
      <div>
        <dt>Unknown outcomes</dt>
        <dd>{{ run.uncertain_count }}</dd>
      </div>
      <div>
        <dt>Not executed</dt>
        <dd>{{ run.not_executed_count }}</dd>
      </div>
      <div>
        <dt>Created matches</dt>
        <dd>{{ run.created_matches_count ?? 'Unknown' }}</dd>
      </div>
      <div>
        <dt>Existing matches skipped</dt>
        <dd>{{ run.existing_matches_skipped_count ?? 'Unknown' }}</dd>
      </div>
    </dl>
    <p v-if="!run.counts_complete" class="unknown-note">
      Some totals are unknown because every outcome has not been acknowledged.
    </p>
    <p v-if="run.tracking_stale" class="stale-note">
      Progress has not updated recently. This is a freshness signal, not a completed state.
    </p>
    <p v-if="run.safe_error_code">Safe run reason: {{ run.safe_error_code }}</p>
  </section>
</template>

<style scoped>
.progress-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: 0.7rem;
}
.headline {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  text-transform: capitalize;
}
progress {
  width: 100%;
  height: 0.8rem;
  accent-color: var(--color-primary);
}
dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: var(--space-3);
  margin: 0;
}
dl div {
  padding: var(--space-2);
  background: var(--color-surface);
  border-radius: var(--radius-control);
}
dt {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}
dd {
  margin: var(--space-1) 0 0;
  font-weight: 650;
}
.unknown-note,
.stale-note {
  color: var(--color-warning-text);
}
</style>
