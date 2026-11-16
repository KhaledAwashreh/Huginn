<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { companyWebsiteUrl } from '../../../shared/lib/externalCompanyUrl';
import RecommendationAssessment from '../../recommendations/components/RecommendationAssessment.vue';
import { activeStageLabel } from '../models/prospect';
import type { ProspectView } from '../models/prospect';
import type {
  ProspectCommandDraft,
  ProspectCommandSubmission,
} from '../models/prospectCommandDraft';
import ProspectFollowUpEditor from './ProspectFollowUpEditor.vue';
import ProspectCurrentSourceContext from './ProspectCurrentSourceContext.vue';
import ProspectHistory from './ProspectHistory.vue';
import ProspectLifecycleActions from './ProspectLifecycleActions.vue';
import ProspectNotesEditor from './ProspectNotesEditor.vue';

const props = defineProps<{
  prospect: ProspectView;
  draft: ProspectCommandDraft;
  disabled: boolean;
  pending: boolean;
  commandError: string;
  canRetry: boolean;
  needsRefresh: boolean;
  completionMessage: string;
}>();
const emit = defineEmits<{
  command: [submission: ProspectCommandSubmission];
  retry: [];
  refresh: [];
  discardDraft: [];
}>();
const lifecycleDisabled = computed(
  () =>
    props.disabled ||
    Boolean(
      props.draft.editor && !['stage', 'close', 'proposal_draft'].includes(props.draft.editor),
    ),
);
const notesDisabled = computed(
  () => props.disabled || Boolean(props.draft.editor && props.draft.editor !== 'notes'),
);
const followUpDisabled = computed(
  () => props.disabled || Boolean(props.draft.editor && props.draft.editor !== 'follow_up'),
);
const historyDisabled = computed(
  () => props.disabled || Boolean(props.draft.editor && props.draft.editor !== 'correction'),
);

function displayTime(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
</script>

<template>
  <article class="prospect-detail" aria-label="Prospect details">
    <header class="prospect-header">
      <div>
        <p class="eyebrow">Saved prospect</p>
        <h2>{{ prospect.company.name }}</h2>
        <a
          v-if="companyWebsiteUrl(prospect.company.domain)"
          :href="companyWebsiteUrl(prospect.company.domain) ?? undefined"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ prospect.company.domain }}
        </a>
        <span v-else>{{ prospect.company.domain }}</span>
      </div>
      <div class="current-state">
        <span class="stage">{{ activeStageLabel(prospect.stage) }}</span>
        <span v-if="prospect.stage === 'closed' && prospect.last_active_stage">
          Last active stage: {{ activeStageLabel(prospect.last_active_stage) }}
        </span>
        <span>Added {{ displayTime(prospect.created_at) }}</span>
      </div>
    </header>

    <div v-if="pending" role="status" class="notice">Saving this prospect update…</div>
    <div v-if="completionMessage" role="status" class="notice">{{ completionMessage }}</div>
    <div v-if="commandError" role="alert" class="error">
      <p>{{ commandError }}</p>
      <div class="actions">
        <Button
          v-if="canRetry"
          label="Retry the exact same request"
          severity="secondary"
          :disabled="pending"
          @click="emit('retry')"
        />
        <Button
          v-if="needsRefresh"
          label="Refresh prospect details"
          severity="secondary"
          :disabled="pending"
          @click="emit('refresh')"
        />
        <Button
          v-if="draft.status === 'stale' || draft.status === 'error'"
          label="Discard draft and reload"
          severity="secondary"
          :disabled="pending"
          @click="emit('discardDraft')"
        />
      </div>
    </div>

    <ProspectCurrentSourceContext
      v-if="prospect.current_source_context"
      :context="prospect.current_source_context"
    />

    <section class="origins" aria-labelledby="prospect-origin-heading">
      <div>
        <h3 id="prospect-origin-heading">Why this prospect was saved</h3>
        <p>
          These assessment details are preserved from the recommendation that created this prospect.
        </p>
      </div>
      <article v-for="origin in prospect.origins" :key="origin.id" class="origin">
        <p class="origin-label">Saved from an assessment on {{ displayTime(origin.created_at) }}</p>
        <RecommendationAssessment
          :assessment="origin.assessment"
          heading="Assessment at this prospect’s origin"
        />
      </article>
      <p v-if="!prospect.origins.length">
        No recommendation origin is available for this prospect.
      </p>
    </section>

    <ProspectLifecycleActions
      :prospect="prospect"
      :draft="draft"
      :disabled="lifecycleDisabled"
      @command="emit('command', $event)"
    />
    <ProspectNotesEditor
      :prospect="prospect"
      :draft="draft"
      :disabled="notesDisabled"
      @command="emit('command', $event)"
    />
    <ProspectFollowUpEditor
      :prospect="prospect"
      :draft="draft"
      :disabled="followUpDisabled"
      @command="emit('command', $event)"
    />
    <ProspectHistory
      :prospect="prospect"
      :draft="draft"
      :disabled="historyDisabled"
      @command="emit('command', { kind: 'correct_activity_time', request: $event })"
    />
  </article>
</template>

<style scoped>
.prospect-detail {
  display: grid;
  gap: var(--space-5);
  min-width: 0;
}
.prospect-header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-3);
}
.eyebrow,
h2,
h3,
p {
  margin-top: 0;
}
.eyebrow {
  margin-bottom: var(--space-1);
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
h2 {
  margin-bottom: var(--space-1);
  font-size: 1.4rem;
  overflow-wrap: anywhere;
}
h3 {
  margin-bottom: var(--space-1);
  font-size: 1.1rem;
}
a {
  color: var(--color-primary);
  overflow-wrap: anywhere;
}
.current-state {
  display: grid;
  align-content: start;
  gap: var(--space-1);
  color: var(--color-text-muted);
  text-align: right;
}
.stage {
  color: var(--color-text);
  font-weight: 650;
  text-transform: capitalize;
}
.origins {
  display: grid;
  gap: var(--space-3);
}
.origins > div > p,
.origin-label {
  margin-bottom: 0;
  color: var(--color-text-muted);
}
.origin {
  display: grid;
  gap: var(--space-2);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-3);
}
.notice,
.error {
  border-radius: var(--radius-control);
  padding: var(--space-3);
  background: var(--color-surface-muted);
}
.error {
  border-inline-start: 3px solid var(--color-danger, #9a3d32);
}
.error p {
  margin-bottom: var(--space-2);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
@media (max-width: 600px) {
  .current-state {
    text-align: left;
  }
}
</style>
