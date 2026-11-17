<script setup lang="ts">
import { computed, reactive, watch, useId } from 'vue';
import Button from 'primevue/button';
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
const reasonId = useId();
const daysId = useId();
const maximumMuteDays = 365;
const muteOpen = computed({
  get: () => draft.value.laterConfirmationOpen,
  set: (value: boolean) => (draft.value.laterConfirmationOpen = value),
});
const activePause = computed(
  () => props.recommendation.active_blocks.find((block) => block.kind === 'pause') ?? null,
);
const muteMode = computed({
  get: () => (draft.value.pauseChoice === 'indefinite' ? 'indefinite' : 'days'),
  set: (value: 'days' | 'indefinite') => {
    draft.value.pauseChoice = value === 'indefinite' ? 'indefinite' : `d${muteDays.value}`;
  },
});
const muteDays = computed({
  get: () => {
    const value = draft.value.pauseChoice;
    return value.startsWith('d') ? Number(value.slice(1)) : 30;
  },
  set: (value: number) => {
    const days = Math.min(maximumMuteDays, Math.max(1, Math.trunc(Number(value) || 1)));
    draft.value.pauseChoice = `d${days}`;
  },
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
const canMute = computed(
  () =>
    Boolean(props.preferences && props.recommendation.assessment) &&
    !commands.pending.value &&
    !disabledByRecovery.value &&
    (muteMode.value === 'indefinite' || (muteDays.value >= 1 && muteDays.value <= maximumMuteDays)),
);
watch([reason, () => draft.value.pauseChoice], () => {
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
function openMute(): void {
  if (!props.recommendation.assessment) return;
  draft.value.snapshot ??= props.recommendation;
  if (draft.value.pauseChoice === 'x1') draft.value.pauseChoice = 'd30';
  muteOpen.value = true;
}
function complete(kind: Completion['kind'], result: unknown): void {
  if (!result) return;
  if (kind === 'saved') {
    if (draft.value.feedback.status === 'error')
      draft.value.feedback = createRecommendationCommandDraft(
        draft.value.recommendationId,
      ).feedback;
    emit('completed', { kind, message: 'Saved as a prospect.' });
  } else if (kind === 'later') {
    const muted = result as { expires_at: string | null };
    emit('completed', {
      kind,
      message: muted.expires_at
        ? `Muted until ${utc(muted.expires_at)} UTC.`
        : 'Muted until you turn it back on.',
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
async function mute(): Promise<void> {
  const preferences = props.preferences;
  const assessment = props.recommendation.assessment;
  if (!preferences || !assessment || !canMute.value) return;
  draft.value.snapshot ??= props.recommendation;
  const choice = muteMode.value === 'indefinite' ? 'indefinite' : `d${muteDays.value}`;
  draft.value.pauseChoice = choice;
  const request = {
    assessment_revision_id: assessment.id,
    expected_pause_id: activePause.value?.id ?? null,
    expected_pause_version: activePause.value?.version ?? null,
    expected_preference_updated_at: preferences.updated_at,
    expected_recommendation_version: props.recommendation.version,
    expected_repeat_interval_days: preferences.repeat_interval_days,
    pause_choice: choice,
    reason: reason.value.trim() || null,
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
        :disabled="
          !recommendation.assessment || !preferences || commands.pending.value || disabledByRecovery
        "
        @click="openMute"
      />
    </div>

    <section v-if="muteOpen" class="mute-panel" aria-label="Mute this company">
      <div class="field">
        <label :for="reasonId">Reason (optional)</label>
        <Textarea
          :id="reasonId"
          v-model="reason"
          rows="2"
          :disabled="commands.pending.value || disabledByRecovery"
        />
      </div>
      <fieldset :disabled="commands.pending.value || disabledByRecovery">
        <legend>How long should this company be muted?</legend>
        <label class="mute-option">
          <input v-model="muteMode" type="radio" value="days" />
          Mute for
          <input
            :id="daysId"
            v-model.number="muteDays"
            type="number"
            min="1"
            :max="maximumMuteDays"
            :disabled="muteMode !== 'days'"
            aria-label="Mute days"
          />
          days
        </label>
        <label class="mute-option">
          <input v-model="muteMode" type="radio" value="indefinite" />
          Until I turn it back on
        </label>
      </fieldset>
      <div class="confirmation-actions">
        <Button label="Confirm" :disabled="!canMute" @click="mute" />
        <Button
          label="Cancel"
          severity="secondary"
          :disabled="commands.pending.value"
          @click="muteOpen = false"
        />
      </div>
      <Button
        v-if="canDiscardDraft"
        label="Discard decision draft"
        severity="secondary"
        @click="discardDraft"
      />
    </section>

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
  padding: var(--space-3) var(--space-5);
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-muted);
  border-radius: 0 0 var(--radius-card) var(--radius-card);
}
.primary-actions,
.recovery-actions,
.confirmation-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}
.primary-actions {
  justify-content: flex-end;
}
.field,
.mute-panel {
  display: grid;
  gap: var(--space-2);
  min-width: min(100%, 18rem);
}
.mute-panel {
  grid-column: 1 / -1;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}
fieldset {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: 0;
}
.mute-option {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
  font-weight: 400;
}
.mute-option input[type='number'] {
  width: 5rem;
}
label {
  font-weight: 600;
}
.unavailable,
.recovery-actions p {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.9rem;
}
.error-inline {
  margin: 0;
  color: var(--color-danger, #a12b32);
}
@media (max-width: 700px) {
  .recommendation-actions {
    padding: var(--space-3) var(--space-4);
  }
  .primary-actions {
    justify-content: flex-start;
  }
}
</style>
