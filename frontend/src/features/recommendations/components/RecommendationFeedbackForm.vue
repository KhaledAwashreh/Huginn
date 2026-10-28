<script setup lang="ts">
import { ref, useId, watch } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';
import Textarea from 'primevue/textarea';
import { ApiError } from '../../../api/apiError';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import { useDirtyDraft } from '../../../shared/forms/useDirtyDraft';
import { saveRecommendationFeedback } from '../api/saveRecommendationFeedback';
import type { RecommendationFeedback, FeedbackReason } from '../models/recommendationFeedback';
import type { RecommendationFeedbackDraft } from '../forms/recommendationFeedbackDraft';
const props = defineProps<{
  batchId: string;
  recommendationId: string;
  history: RecommendationFeedback[];
}>();
const emit = defineEmits<{ saved: [RecommendationFeedback]; dirty: [boolean] }>();
const id = useId();
const { draft, dirty, accept } = useDirtyDraft<RecommendationFeedbackDraft>({
  recommendation_id: props.recommendationId,
  usefulness: 'unsure',
  reasons: [],
  correction: '',
  next_step: 'none',
  outcome: 'not_contacted',
  notes: '',
});
watch(dirty, (value) => {
  emit('dirty', value);
  if (value) saved.value = false;
});
const pending = ref(false);
const error = ref('');
const saved = ref(false);
const reasons: { value: FeedbackReason; label: string }[] = [
  { value: 'service_fit', label: 'Service fit' },
  { value: 'company_fit', label: 'Company fit' },
  { value: 'timing', label: 'Timing' },
  { value: 'geography', label: 'Geography' },
  { value: 'evidence_wrong', label: 'Incorrect evidence' },
  { value: 'customer_not_buyer', label: 'Customer is not the buyer' },
  { value: 'already_known', label: 'Already known' },
  { value: 'other', label: 'Other' },
];
const usefulness = [
  { value: 'useful', label: 'Useful' },
  { value: 'not_useful', label: 'Not useful' },
  { value: 'unsure', label: 'Unsure' },
];
const nextSteps = [
  { value: 'none', label: 'No next step' },
  { value: 'research', label: 'Research' },
  { value: 'contact', label: 'Contact' },
  { value: 'save', label: 'Save for later' },
  { value: 'skip', label: 'Skip' },
];
const outcomes = [
  { value: 'not_contacted', label: 'Not contacted' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'replied', label: 'Replied' },
  { value: 'meeting', label: 'Meeting' },
  { value: 'won', label: 'Won' },
  { value: 'not_relevant', label: 'Not relevant' },
  { value: 'unknown', label: 'Unknown' },
];
function label(value: string) {
  return (
    [...usefulness, ...nextSteps, ...outcomes, ...reasons].find((option) => option.value === value)
      ?.label ?? value
  );
}
async function save() {
  if (pending.value) return;
  pending.value = true;
  error.value = '';
  saved.value = false;
  const submitted = structuredClone({ ...draft.value, reasons: [...draft.value.reasons] });
  try {
    const feedback = await saveRecommendationFeedback(props.batchId, submitted);
    if (
      feedback.batch_id !== props.batchId ||
      feedback.recommendation_id !== props.recommendationId
    )
      throw new Error('Feedback receipt does not match this assessment.');
    accept(submitted);
    saved.value = true;
    emit('saved', feedback);
  } catch (cause) {
    error.value =
      cause instanceof ApiError && cause.status === 403
        ? 'Reload the page before saving. Your feedback is preserved.'
        : 'Feedback could not be saved. Your entries are preserved; try again.';
  } finally {
    pending.value = false;
  }
}
</script>
<template>
  <section aria-label="Feedback">
    <h3>Your assessment</h3>
    <p>
      Record what helped, correct the research, or add a later outreach outcome. Each save adds to
      this assessment’s history.
    </p>
    <form class="feedback-form" @submit.prevent="save">
      <fieldset :disabled="pending">
        <legend>Recommendation feedback</legend>
        <div class="field">
          <label :for="`${id}-usefulness`">How useful is this recommendation?</label
          ><Select
            v-model="draft.usefulness"
            :disabled="pending"
            :input-id="`${id}-usefulness`"
            aria-label="How useful is this recommendation?"
            :options="usefulness"
            option-label="label"
            option-value="value"
          />
        </div>
        <fieldset>
          <legend>Reasons (optional)</legend>
          <div class="reasons">
            <label v-for="reason in reasons" :key="reason.value"
              ><input v-model="draft.reasons" type="checkbox" :value="reason.value" />
              {{ reason.label }}</label
            >
          </div>
        </fieldset>
        <div class="field">
          <label :for="`${id}-correction`">Correction or missing context</label
          ><Textarea
            :id="`${id}-correction`"
            v-model="draft.correction"
            :maxlength="2000"
            rows="3"
          />
        </div>
        <div class="field">
          <label :for="`${id}-next`">Next step</label
          ><Select
            v-model="draft.next_step"
            :disabled="pending"
            :input-id="`${id}-next`"
            aria-label="Next step"
            :options="nextSteps"
            option-label="label"
            option-value="value"
          />
        </div>
        <div class="field">
          <label :for="`${id}-outcome`">Outreach outcome</label
          ><Select
            v-model="draft.outcome"
            :disabled="pending"
            :input-id="`${id}-outcome`"
            aria-label="Outreach outcome"
            :options="outcomes"
            option-label="label"
            option-value="value"
          />
        </div>
        <div class="field">
          <label :for="`${id}-notes`">Notes</label
          ><Textarea :id="`${id}-notes`" v-model="draft.notes" :maxlength="4000" rows="3" />
        </div>
      </fieldset>
      <ErrorState v-if="error" :message="error" />
      <div class="form-actions">
        <Button
          type="submit"
          :label="pending ? 'Saving feedback…' : 'Save feedback'"
          :disabled="pending"
        /><span v-if="saved" role="status">Feedback saved.</span
        ><span v-else-if="dirty">Unsaved feedback</span>
      </div>
    </form>
    <h3>Feedback history</h3>
    <p v-if="!history.length">No feedback recorded yet.</p>
    <ol v-else class="history">
      <li v-for="entry in history" :key="entry.id">
        <time :datetime="entry.created_at">{{ new Date(entry.created_at).toLocaleString() }}</time>
        · {{ label(entry.usefulness) }} · {{ label(entry.next_step) }} · {{ label(entry.outcome) }}
        <p v-if="entry.reasons?.length">Reasons: {{ entry.reasons.map(label).join(', ') }}</p>
        <p v-if="entry.correction">Correction: {{ entry.correction }}</p>
        <p v-if="entry.notes">{{ entry.notes }}</p>
      </li>
    </ol>
  </section>
</template>
<style scoped>
.feedback-form,
fieldset,
.field {
  display: grid;
  gap: var(--space-3);
}
fieldset {
  min-width: 0;
  border: 1px solid var(--color-border);
  padding: var(--space-4);
  border-radius: var(--radius-control);
}
.reasons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: var(--space-2);
}
.history {
  padding-left: var(--space-6);
}
.history li {
  padding-bottom: var(--space-4);
  overflow-wrap: anywhere;
}
</style>
