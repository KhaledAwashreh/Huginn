<script setup lang="ts">
import type { components } from '../../../api/generated/schema';
import ProspectActivityTimeCorrection from './ProspectActivityTimeCorrection.vue';
import {
  activityLabel,
  activitySummary,
  orderProspectActivities,
} from '../models/prospectActivityTimeline';
import type { ProspectView } from '../models/prospect';
import type { ProspectCommandDraft } from '../models/prospectCommandDraft';

const props = defineProps<{
  prospect: ProspectView;
  draft: ProspectCommandDraft;
  disabled: boolean;
}>();
const emit = defineEmits<{
  command: [request: components['schemas']['CorrectProspectActivityTimeRequest']];
}>();
const history = () => orderProspectActivities(props.prospect.activities ?? []);
function recordedAt(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
</script>

<template>
  <section class="prospect-history" aria-labelledby="prospect-history-heading">
    <div class="section-heading">
      <div>
        <h2 id="prospect-history-heading">History</h2>
        <p>Recorded actions are retained. Correcting a time appends a separate history entry.</p>
      </div>
    </div>
    <ol v-if="history().length" class="timeline">
      <li v-for="activity in history()" :key="activity.id">
        <div class="event-heading">
          <strong>{{ activityLabel(activity.kind) }}</strong>
          <time :datetime="activity.recorded_at"
            >Recorded {{ recordedAt(activity.recorded_at) }}</time
          >
        </div>
        <p v-if="activitySummary(activity)">{{ activitySummary(activity) }}</p>
        <p>
          Effective occurrence:
          <time :datetime="activity.effective_occurred_at">{{
            recordedAt(activity.effective_occurred_at)
          }}</time>
        </p>
        <p v-if="activity.correction_of_id">
          Corrects an earlier activity. The original remains unchanged.
        </p>
        <ProspectActivityTimeCorrection
          :activity="activity"
          :prospect-version="prospect.version"
          :draft="draft"
          :disabled="disabled"
          @command="emit('command', $event)"
        />
      </li>
    </ol>
    <p v-else>No activity has been recorded for this prospect yet.</p>
  </section>
</template>

<style scoped>
.prospect-history,
.timeline {
  display: grid;
  gap: var(--space-3);
}
.section-heading,
.event-heading {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-2);
  align-items: baseline;
}
h2,
p {
  margin-top: 0;
}
h2 {
  margin-bottom: var(--space-1);
  font-size: 1.1rem;
}
.section-heading p,
.event-heading time,
.timeline li > p {
  color: var(--color-text-muted);
}
.section-heading p,
.timeline li > p {
  margin-bottom: 0;
}
.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}
.timeline li {
  display: grid;
  gap: var(--space-2);
  border-left: 2px solid var(--color-border);
  padding: 0 0 var(--space-3) var(--space-3);
  min-width: 0;
}
.timeline li:last-child {
  padding-bottom: 0;
}
</style>
