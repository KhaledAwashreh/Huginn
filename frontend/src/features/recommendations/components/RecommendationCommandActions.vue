<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch, useId } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';
import Textarea from 'primevue/textarea';
import { useRecommendationCommands } from '../composables/useRecommendationCommands';
import type {
  RecommendationCommandDraft,
  RecommendationCommandIntent,
} from '../models/recommendationCommandDraft';
import {
  createRecommendationCommandDraft,
  resetRecommendationDecisionDraft,
} from '../models/recommendationCommandDraft';
import type { RecommendationView } from '../models/prospecting';
import type { RecommendationPreferences } from '../models/prospecting';

type Completion = { kind: 'saved' | 'not_relevant' | 'later'; message: string };
const props = defineProps<{
  recommendation: RecommendationView;
  preferences: RecommendationPreferences | null;
  preferencesLoading: boolean;
  preferencesFailed: boolean;
  identity: string;
  draftState?: RecommendationCommandDraft;
  refreshPreferences?: () => Promise<RecommendationPreferences>;
}>();
const emit = defineEmits<{ completed: [Completion] }>();
const commands = useRecommendationCommands(computed(() => props.identity));
const localDraft = reactive(createRecommendationCommandDraft(props.recommendation.id));
const draft = computed(() => props.draftState ?? localDraft);
const reason = computed({
  get: () => draft.value.reason,
  set: (value: string) => (draft.value.reason = value),
});
const choice = computed({
  get: () => draft.value.pauseChoice,
  set: (value: RecommendationCommandDraft['pauseChoice']) => (draft.value.pauseChoice = value),
});
const choiceId = useId();
const reasonId = useId();
const reasonDescriptionId = useId();
const explanationId = useId();
const confirmationId = useId();
const laterConfirmationOpen = computed({
  get: () => draft.value.laterConfirmationOpen,
  set: (value: boolean) => (draft.value.laterConfirmationOpen = value),
});
const refreshingPreferences = ref(false);
const confirmationPreferences = ref<RecommendationPreferences | null>(null);
const previewError = ref('');
const clockNow = ref(Date.now());
let clockInterval: number | undefined;
const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
const cadenceDays = computed(() => {
  const preferences = confirmationPreferences.value ?? props.preferences;
  if (!preferences || choice.value === 'indefinite') return null;
  const multiplier = Number(choice.value.slice(1));
  return preferences.repeat_interval_days * multiplier;
});
const activePause = computed(
  () => props.recommendation.active_blocks.find((block) => block.kind === 'pause') ?? null,
);
const laterSummary = computed(() => {
  if (choice.value === 'indefinite') return 'Pause recommendations indefinitely.';
  if (cadenceDays.value === null) return 'Loading your Business repeat interval…';
  const preferences = confirmationPreferences.value ?? props.preferences;
  return `Pause for ${choice.value.slice(1)} × ${preferences?.repeat_interval_days}-day repeat interval (${cadenceDays.value} days).`;
});
const previewExpiry = computed(() =>
  cadenceDays.value === null ? null : new Date(clockNow.value + cadenceDays.value * 86_400_000),
);
const options = [
  { label: 'x1 · one repeat interval', value: 'x1' },
  { label: 'x2 · two repeat intervals', value: 'x2' },
  { label: 'x3 · three repeat intervals', value: 'x3' },
  { label: 'x4 · four repeat intervals', value: 'x4' },
  { label: 'Indefinite', value: 'indefinite' },
];
onMounted(() => {
  clockInterval = window.setInterval(() => {
    clockNow.value = Date.now();
  }, 1000);
  if (laterConfirmationOpen.value) void refreshPreview();
});
onUnmounted(() => {
  if (clockInterval !== undefined) window.clearInterval(clockInterval);
});
const disabledByRecovery = computed(
  () =>
    draft.value.status === 'pending' ||
    draft.value.status === 'uncertain' ||
    draft.value.status === 'stale',
);
const canDiscardDraft = computed(
  () =>
    !disabledByRecovery.value &&
    (draft.value.reason.trim() !== '' ||
      draft.value.pauseChoice !== 'x1' ||
      draft.value.laterConfirmationOpen ||
      draft.value.status === 'editing' ||
      draft.value.error !== ''),
);
watch([reason, choice], () => {
  if (disabledByRecovery.value) return;
  draft.value.snapshot ??= props.recommendation;
  draft.value.status = 'idle';
  draft.value.intent = null;
  draft.value.error = '';
  commands.clearError();
});

function key(): string {
  return crypto.randomUUID();
}
function utc(value: string): string {
  return new Date(value).toISOString().replace('T', ' ').replace('Z', '');
}
function localDateTime(value: Date): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'long',
    timeZone,
  }).format(value);
}
function utcDateTime(value: Date): string {
  return value.toISOString().replace('T', ' ').replace('Z', ' UTC');
}
async function refreshPreview(): Promise<void> {
  previewError.value = '';
  if (!props.refreshPreferences) {
    confirmationPreferences.value = props.preferences;
    clockNow.value = Date.now();
    return;
  }
  refreshingPreferences.value = true;
  try {
    confirmationPreferences.value = await props.refreshPreferences();
    clockNow.value = Date.now();
  } catch {
    previewError.value =
      'Business repeat timing could not be refreshed. Your selected duration is preserved.';
  } finally {
    refreshingPreferences.value = false;
  }
}
async function openLaterConfirmation(): Promise<void> {
  if (!props.preferences || !props.recommendation.assessment) return;
  draft.value.snapshot ??= props.recommendation;
  laterConfirmationOpen.value = true;
  await refreshPreview();
}
function blockers(values: string[]): string {
  return values.length ? values.map((value) => value.replaceAll('_', ' ')).join(', ') : 'none';
}
function complete(kind: Completion['kind'], result: unknown): void {
  if (!result) return;
  if (kind === 'saved') {
    emit('completed', { kind, message: 'Saved as a prospect.' });
  } else if (kind === 'not_relevant') {
    emit('completed', {
      kind,
      message:
        'Marked not relevant. This creates a persistent Company block until you reverse the rejection in Manage suppressions.',
    });
  } else {
    const later = result as {
      expires_at: string | null;
      selected_at: string;
      pause_choice: string;
      repeat_interval_days: number;
      remaining_blockers: string[];
    };
    const accepted = `Accepted at ${utc(later.selected_at)} UTC`;
    const duration =
      later.pause_choice === 'indefinite'
        ? 'Indefinite pause'
        : `${later.pause_choice.toUpperCase()} × ${later.repeat_interval_days}-day repeat interval`;
    emit('completed', {
      kind,
      message: later.expires_at
        ? `${duration}. ${accepted}; paused until ${utc(later.expires_at)} UTC. Remaining independent blockers: ${blockers(later.remaining_blockers)}.`
        : `${duration}. ${accepted}. Remaining independent blockers: ${blockers(later.remaining_blockers)}.`,
    });
  }
  resetRecommendationDecisionDraft(draft.value);
}
function discardDraft(): void {
  if (!canDiscardDraft.value) return;
  resetRecommendationDecisionDraft(draft.value);
}
async function executeIntent(intent: RecommendationCommandIntent): Promise<void> {
  const targetDraft = draft.value;
  await commands.executeDecision(
    intent,
    targetDraft,
    (result) => complete(intent.kind, result),
    () => intent.identity === props.identity && targetDraft === draft.value,
  );
}

async function save(): Promise<void> {
  const assessment = props.recommendation.assessment;
  if (!assessment) return;
  draft.value.snapshot ??= props.recommendation;
  const request = {
    assessment_revision_id: assessment.id,
    request_key: key(),
  };
  await executeIntent({
    kind: 'saved',
    identity: props.identity,
    recommendationId: props.recommendation.id,
    request,
  });
}
async function reject(): Promise<void> {
  const assessment = props.recommendation.assessment;
  if (!assessment) return;
  draft.value.snapshot ??= props.recommendation;
  const request = {
    assessment_revision_id: assessment.id,
    expected_recommendation_version: props.recommendation.version,
    reason: reason.value.trim() || null,
    request_key: key(),
  };
  await executeIntent({
    kind: 'not_relevant',
    identity: props.identity,
    recommendationId: props.recommendation.id,
    request,
  });
}
async function later(): Promise<void> {
  const capturedPreferences = confirmationPreferences.value;
  if (!capturedPreferences || !props.recommendation.assessment || refreshingPreferences.value)
    return;
  draft.value.snapshot ??= props.recommendation;
  refreshingPreferences.value = true;
  let preferences: RecommendationPreferences;
  try {
    preferences = props.refreshPreferences ? await props.refreshPreferences() : capturedPreferences;
  } catch {
    previewError.value =
      'Business repeat timing could not be refreshed. Review the cadence before confirming.';
    return;
  } finally {
    refreshingPreferences.value = false;
  }
  if (
    preferences.updated_at !== capturedPreferences.updated_at ||
    preferences.repeat_interval_days !== capturedPreferences.repeat_interval_days
  ) {
    confirmationPreferences.value = preferences;
    clockNow.value = Date.now();
    previewError.value =
      'Business repeat timing changed. Review the updated duration and end time before confirming.';
    return;
  }
  previewError.value = '';
  const request = {
    assessment_revision_id: props.recommendation.assessment.id,
    expected_pause_id: activePause.value?.id ?? null,
    expected_pause_version: activePause.value?.version ?? null,
    expected_preference_updated_at: preferences.updated_at,
    expected_recommendation_version: props.recommendation.version,
    expected_repeat_interval_days: preferences.repeat_interval_days,
    pause_choice: choice.value,
    request_key: key(),
  };
  await executeIntent({
    kind: 'later',
    identity: props.identity,
    recommendationId: props.recommendation.id,
    request,
  });
}
async function retry(): Promise<void> {
  const intent = draft.value.intent;
  if (intent) await executeIntent(intent);
}
async function refresh(): Promise<void> {
  try {
    await commands.refresh();
    if (laterConfirmationOpen.value) await refreshPreview();
    draft.value.intent = null;
    draft.value.status = 'idle';
    draft.value.error = '';
  } catch {
    draft.value.error =
      'Current recommendation state could not be refreshed. Your draft is preserved.';
  }
}
</script>

<template>
  <section class="recommendation-actions" aria-label="Recommendation decisions">
    <p v-if="!recommendation.assessment" class="unavailable">
      A shown assessment is required before saving or recording a decision.
    </p>
    <div class="primary-actions">
      <Button
        label="Save as prospect"
        :disabled="!recommendation.assessment || commands.pending.value || disabledByRecovery"
        @click="save"
      />
      <Button
        label="Not relevant"
        severity="secondary"
        :disabled="!recommendation.assessment || commands.pending.value || disabledByRecovery"
        @click="reject"
      />
    </div>
    <p class="disclosure">
      Save as prospect creates a Saved prospect and retains this exact assessment revision as its
      origin.
    </p>
    <p class="disclosure">
      Not relevant resolves this recommendation and blocks future discovery of this Company until
      you reverse the rejection in Manage suppressions. It does not create a prospect or clear
      unrelated blocks.
    </p>
    <div class="field">
      <label :for="reasonId">Reason (optional)</label>
      <Textarea
        :id="reasonId"
        v-model="reason"
        rows="2"
        :disabled="commands.pending.value || disabledByRecovery"
        :aria-describedby="reasonDescriptionId"
      />
      <span :id="reasonDescriptionId" class="sr-only">
        This reason is stored with the persistent Company rejection.
      </span>
    </div>
    <div class="later-choice">
      <div class="field">
        <label :for="choiceId">Later duration</label>
        <Select
          v-model="choice"
          :input-id="choiceId"
          :options="options"
          option-label="label"
          option-value="value"
          :disabled="commands.pending.value || disabledByRecovery"
          :aria-describedby="explanationId"
        />
      </div>
      <p :id="explanationId" class="disclosure">
        {{ laterSummary }}
        <span v-if="activePause">
          This replaces the current pause with a new duration from your acceptance time; prior pause
          history remains recorded.
        </span>
        <span v-else>Any other independent block remains in place.</span>
      </p>
      <Button
        label="Review Later"
        severity="secondary"
        :disabled="
          !preferences || !recommendation.assessment || commands.pending.value || disabledByRecovery
        "
        @click="openLaterConfirmation"
      />
      <section
        v-if="laterConfirmationOpen"
        :id="confirmationId"
        class="later-confirmation"
        aria-label="Confirm Later decision"
        aria-live="polite"
      >
        <p v-if="choice === 'indefinite'">
          If you pause now, recommendations will have no expiry. The pause starts when confirmed;
          the server will report the accepted time.
        </p>
        <p v-else-if="previewExpiry" data-testid="later-expiry-preview">
          If you pause now, recommendations will resume after
          {{ confirmationPreferences?.repeat_interval_days }} × {{ choice.slice(1) }} days ({{
            cadenceDays
          }}
          days), on {{ localDateTime(previewExpiry) }} ({{ timeZone }}),
          {{ utcDateTime(previewExpiry) }}. This is a live estimate; the pause starts when
          confirmed, and the confirmation will show when the pause starts and ends.
        </p>
        <p v-if="activePause">
          This replaces the current
          {{
            activePause.expires_at
              ? `pause through ${localDateTime(new Date(activePause.expires_at))}`
              : 'indefinite pause'
          }}. The prior pause remains in history.
        </p>
        <p v-if="recommendation.selection_blockers.length" class="disclosure">
          Other independent blockers remain: {{ blockers(recommendation.selection_blockers) }}.
        </p>
        <p v-if="previewError" class="error-inline" role="alert">{{ previewError }}</p>
        <div class="confirmation-actions">
          <Button
            label="Refresh preview"
            severity="secondary"
            :disabled="refreshingPreferences || commands.pending.value"
            @click="refreshPreview"
          />
          <Button
            label="Confirm Later"
            :disabled="!confirmationPreferences || refreshingPreferences || disabledByRecovery"
            @click="later"
          />
          <Button
            label="Cancel"
            severity="secondary"
            :disabled="refreshingPreferences || commands.pending.value"
            @click="laterConfirmationOpen = false"
          />
        </div>
      </section>
      <p v-if="preferencesFailed" class="error-inline">
        Business repeat timing could not be loaded. Reload the cadence before choosing Later.
      </p>
      <Button
        v-if="preferencesFailed"
        label="Retry repeat timing"
        text
        :disabled="commands.pending.value"
        @click="commands.refresh"
      />
      <Button
        v-if="canDiscardDraft"
        label="Discard decision draft"
        severity="secondary"
        @click="discardDraft"
      />
    </div>
    <p v-if="draft.error" class="error-inline" role="alert">{{ draft.error }}</p>
    <div v-if="draft.status === 'pending'" class="recovery-actions" role="status">
      <p>
        The submitted decision is still being checked. This action will not be submitted again
        automatically.
      </p>
    </div>
    <div v-if="draft.status === 'uncertain'" class="recovery-actions">
      <Button
        label="Retry the same request"
        severity="secondary"
        :disabled="commands.pending.value"
        @click="retry"
      />
      <p>Retrying checks this same decision safely without creating a duplicate.</p>
    </div>
    <Button
      v-if="draft.status === 'stale'"
      label="Refresh current state"
      severity="secondary"
      :disabled="commands.pending.value"
      @click="refresh"
    />
  </section>
</template>

<style scoped>
.recommendation-actions {
  display: grid;
  gap: var(--space-3);
  min-width: 0;
}
.primary-actions,
.recovery-actions,
.confirmation-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}
.field {
  display: grid;
  gap: var(--space-1);
  min-width: min(100%, 18rem);
}
label {
  font-weight: 600;
}
.disclosure,
.unavailable,
.recovery-actions p {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.9rem;
}
.later-choice {
  display: grid;
  grid-template-columns: minmax(12rem, 1fr) auto;
  gap: var(--space-2);
  align-items: end;
}
.later-choice .disclosure {
  grid-column: 1 / -1;
}
.later-confirmation {
  display: grid;
  gap: var(--space-2);
  grid-column: 1 / -1;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}
.later-confirmation > p {
  margin: 0;
}
.error-inline {
  margin: 0;
  color: var(--color-danger, #a12b32);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
@media (max-width: 36rem) {
  .later-choice {
    grid-template-columns: 1fr;
  }
  .later-choice .disclosure {
    grid-column: auto;
  }
}
</style>
