<script setup lang="ts">
import { computed, onBeforeUnmount, useId } from 'vue';
import Button from 'primevue/button';
import { ApiError } from '../../../api/apiError';
import { recordRecommendationFeedback } from '../api/recordRecommendationFeedback';
import type {
  RecommendationCommandDraft,
  RecommendationFeedbackIntent,
} from '../models/recommendationCommandDraft';
import type { RecommendationView } from '../models/prospecting';

const props = defineProps<{
  recommendation: RecommendationView;
  identity: string;
  draftState: RecommendationCommandDraft;
}>();
const titleId = useId();
const helpId = useId();
const commandDraft = computed(() => props.draftState);
const feedbackDraft = computed(() => commandDraft.value.feedback);
const busy = computed(() => feedbackDraft.value.status === 'pending');
const locked = computed(() => busy.value || feedbackDraft.value.status === 'uncertain');
const reasons: RecommendationCommandDraft['feedback']['reasons'] = [
  'service_fit',
  'company_fit',
  'timing',
  'geography',
  'evidence_wrong',
  'customer_not_buyer',
  'already_known',
  'other',
];
const outcomes: RecommendationCommandDraft['feedback']['outcome'][] = [
  'unknown',
  'not_contacted',
  'contacted',
  'replied',
  'meeting',
  'won',
  'not_relevant',
];
const nextSteps: RecommendationCommandDraft['feedback']['next_step'][] = [
  'none',
  'research',
  'contact',
  'save',
  'skip',
];
function key(): string {
  return crypto.randomUUID();
}
function discard(): void {
  const form = feedbackDraft.value;
  form.open = false;
  form.usefulness = 'unsure';
  form.reasons = [];
  form.outcome = 'unknown';
  form.next_step = 'none';
  form.correction = '';
  form.notes = '';
  form.status = 'idle';
  form.error = '';
  form.intent = null;
  if (
    commandDraft.value.status === 'idle' &&
    !commandDraft.value.intent &&
    !commandDraft.value.reason &&
    commandDraft.value.pauseChoice === 'x1' &&
    !commandDraft.value.laterConfirmationOpen
  )
    commandDraft.value.snapshot = null;
}
onBeforeUnmount(() => {
  if (!locked.value) discard();
});
function label(value: string): string {
  return value.replaceAll('_', ' ');
}
function makeIntent(): RecommendationFeedbackIntent {
  const assessment = props.recommendation.assessment;
  if (!assessment) throw new Error('The shown assessment is no longer available.');
  commandDraft.value.snapshot ??= props.recommendation;
  return {
    identity: props.identity,
    recommendationId: props.recommendation.id,
    request: {
      assessment_revision_id: assessment.id,
      request_key: key(),
      feedback: {
        usefulness: feedbackDraft.value.usefulness,
        reasons: [...feedbackDraft.value.reasons],
        outcome: feedbackDraft.value.outcome,
        next_step: feedbackDraft.value.next_step,
        correction: feedbackDraft.value.correction,
        notes: feedbackDraft.value.notes,
      },
    },
  };
}
async function send(intent: RecommendationFeedbackIntent): Promise<void> {
  const parentDraft = commandDraft.value;
  const state = feedbackDraft.value;
  if (intent.identity !== props.identity) return;
  state.intent = intent;
  state.status = 'pending';
  state.error = '';
  try {
    await recordRecommendationFeedback(intent.recommendationId, intent.request);
    if (props.identity !== intent.identity || commandDraft.value !== parentDraft) return;
    state.intent = null;
    state.status = 'idle';
    state.error =
      'Feedback recorded. This report does not change your recommendation or its ranking.';
    state.open = false;
    state.usefulness = 'unsure';
    state.reasons = [];
    state.outcome = 'unknown';
    state.next_step = 'none';
    state.correction = '';
    state.notes = '';
    if (parentDraft.status === 'idle' && !parentDraft.reason && parentDraft.pauseChoice === 'x1')
      parentDraft.snapshot = null;
  } catch (error) {
    if (props.identity !== intent.identity || commandDraft.value !== parentDraft) return;
    if (error instanceof ApiError && error.status < 500) {
      state.intent = null;
      state.status = 'error';
      state.error = 'Feedback was not accepted. Review the report and try again.';
    } else {
      state.status = 'uncertain';
      state.error =
        'We could not confirm whether your report was saved. Retry the same report safely.';
    }
  }
}
async function submit(): Promise<void> {
  if (!props.recommendation.assessment || locked.value) return;
  const intent = feedbackDraft.value.intent ?? makeIntent();
  await send(intent);
}
async function retry(): Promise<void> {
  if (!feedbackDraft.value.intent || feedbackDraft.value.intent.identity !== props.identity) return;
  await send(feedbackDraft.value.intent);
}
</script>

<template>
  <section class="quality-feedback" :aria-labelledby="titleId">
    <h3 :id="titleId">Recommendation feedback</h3>
    <p :id="helpId" class="disclosure">
      Tell us what you learned about this recommendation. Feedback does not change the
      recommendation, company blocks, configuration, eligibility, or ranking.
    </p>
    <form @submit.prevent="submit">
      <label>
        How useful was this assessment?
        <select v-model="feedbackDraft.usefulness" :disabled="locked" :aria-describedby="helpId">
          <option value="unsure">Unsure</option>
          <option value="useful">Useful</option>
          <option value="not_useful">Not useful</option>
        </select>
      </label>
      <fieldset :disabled="locked">
        <legend>What should we learn?</legend>
        <label v-for="reason in reasons" :key="reason">
          <input v-model="feedbackDraft.reasons" type="checkbox" :value="reason" />
          {{ label(reason) }}
        </label>
      </fieldset>
      <label>
        Outcome
        <select v-model="feedbackDraft.outcome" :disabled="locked">
          <option v-for="outcome in outcomes" :key="outcome" :value="outcome">
            {{ label(outcome) }}
          </option>
        </select>
      </label>
      <label>
        Suggested next step
        <select v-model="feedbackDraft.next_step" :disabled="locked">
          <option v-for="step in nextSteps" :key="step" :value="step">{{ label(step) }}</option>
        </select>
      </label>
      <label>
        Correction
        <textarea v-model="feedbackDraft.correction" :disabled="locked" rows="2" />
      </label>
      <label>
        Notes
        <textarea v-model="feedbackDraft.notes" :disabled="locked" rows="2" />
      </label>
      <Button
        v-if="feedbackDraft.status === 'uncertain'"
        label="Retry the same report"
        severity="secondary"
        :disabled="busy"
        @click="retry"
      />
      <Button
        v-else
        type="submit"
        label="Submit assessment report"
        :disabled="!recommendation.assessment || busy"
      />
      <Button
        v-if="feedbackDraft.status !== 'uncertain' && feedbackDraft.status !== 'pending'"
        label="Discard report draft"
        severity="secondary"
        @click="discard"
      />
    </form>
    <p
      v-if="feedbackDraft.error"
      :role="
        feedbackDraft.status === 'uncertain' || feedbackDraft.status === 'error'
          ? 'alert'
          : 'status'
      "
    >
      {{ feedbackDraft.error }}
    </p>
  </section>
</template>

<style scoped>
.quality-feedback {
  display: grid;
  gap: var(--space-2);
  border-top: 1px solid var(--color-border);
  padding: var(--space-4) var(--space-5);
}
h3,
p {
  margin: 0;
}
form {
  display: grid;
  gap: var(--space-3);
  max-width: 38rem;
}
form > label,
fieldset {
  display: grid;
  gap: var(--space-1);
}
fieldset {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}
fieldset label {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
select,
textarea {
  width: 100%;
}
</style>
