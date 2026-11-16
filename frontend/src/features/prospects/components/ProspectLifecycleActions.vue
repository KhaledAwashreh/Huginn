<script setup lang="ts">
import { computed, useId } from 'vue';
import Button from 'primevue/button';
import type { components } from '../../../api/generated/schema';
import type { ProspectView } from '../models/prospect';
import { activeStageLabel, prospectStageActions } from '../models/prospect';
import type {
  ProspectCommandDraft,
  ProspectCommandSubmission,
} from '../models/prospectCommandDraft';
import { cancelProspectDraft, startProspectDraft } from '../models/prospectCommandDraft';

const props = defineProps<{
  prospect: ProspectView;
  draft: ProspectCommandDraft;
  disabled: boolean;
}>();
const emit = defineEmits<{ command: [submission: ProspectCommandSubmission] }>();
const draft = computed(() => props.draft);
const reasonId = useId();
const occurredAtId = useId();
const stages = computed(() => prospectStageActions(props.prospect.stage));
const selectedAction = computed(() =>
  draft.value.editor === 'stage'
    ? (stages.value.find((action) => action.target === draft.value.stageTarget) ?? null)
    : null,
);
const canClose = computed(() =>
  ['saved', 'contacted', 'in_conversation', 'proposal_sent'].includes(props.prospect.stage),
);
const isReopening = computed(() => props.prospect.stage === 'closed');

function beginStage(action: { target: ProspectView['stage'] }): void {
  if (props.disabled) return;
  startProspectDraft(draft.value, props.prospect.version);
  draft.value.editor = 'stage';
  draft.value.stageTarget = action.target;
  draft.value.reason = '';
  beginOccurrenceTime();
}
function cancelStage(): void {
  if (draft.value.status === 'pending' || draft.value.status === 'uncertain') return;
  cancelProspectDraft(draft.value);
}
function occurredAt(): string {
  return new Date(draft.value.occurredAt || Date.now()).toISOString();
}
function localDateTime(value: Date): string {
  const date = new Date(value);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}
function beginOccurrenceTime(): void {
  if (!draft.value.occurredAt) draft.value.occurredAt = localDateTime(new Date());
}
function requestKey(): string {
  return crypto.randomUUID();
}
function submitStage(): void {
  const action = selectedAction.value;
  const expectedVersion = draft.value.expectedVersion;
  if (!action || expectedVersion === null || !draft.value.occurredAt || props.disabled) return;
  if (action.requiresReason && !draft.value.reason.trim()) return;
  const request: components['schemas']['ChangeProspectStageRequest'] = {
    expected_version: expectedVersion,
    occurred_at: occurredAt(),
    target_stage:
      action.target as components['schemas']['ChangeProspectStageRequest']['target_stage'],
    reason: draft.value.reason.trim() || null,
    request_key: requestKey(),
  };
  emit('command', { kind: 'stage', request });
}
function submitClose(): void {
  const expectedVersion = draft.value.expectedVersion;
  if (
    !canClose.value ||
    expectedVersion === null ||
    !draft.value.occurredAt ||
    !draft.value.reason.trim() ||
    props.disabled
  )
    return;
  emit('command', {
    kind: 'close',
    request: {
      expected_version: expectedVersion,
      occurred_at: occurredAt(),
      reason: draft.value.reason.trim(),
      request_key: requestKey(),
    },
  });
}
function closeForm(): void {
  if (props.disabled) return;
  startProspectDraft(draft.value, props.prospect.version);
  draft.value.editor = 'close';
  draft.value.stageTarget = null;
  draft.value.reason = '';
  beginOccurrenceTime();
}
function reopen(): void {
  if (!isReopening.value || props.disabled) return;
  startProspectDraft(draft.value, props.prospect.version);
  const expectedVersion = draft.value.expectedVersion;
  if (expectedVersion === null) return;
  emit('command', {
    kind: 'reopen',
    request: {
      expected_version: expectedVersion,
      occurred_at: occurredAt(),
      request_key: requestKey(),
    },
  });
}
function beginProposalDraft(): void {
  if (props.disabled) return;
  startProspectDraft(draft.value, props.prospect.version);
  draft.value.editor = 'proposal_draft';
  draft.value.stageTarget = 'proposal_sent';
  draft.value.proposalSummary = '';
}
function saveProposalDraft(): void {
  const expectedVersion = draft.value.expectedVersion;
  if (expectedVersion === null || !draft.value.proposalSummary.trim() || props.disabled) return;
  emit('command', {
    kind: 'proposal_draft',
    request: {
      expected_version: expectedVersion,
      occurred_at: occurredAt(),
      summary: draft.value.proposalSummary.trim(),
      request_key: requestKey(),
    },
  });
}
</script>

<template>
  <section class="lifecycle-actions" aria-labelledby="lifecycle-heading">
    <h2 id="lifecycle-heading">Prospect actions</h2>
    <p class="current-stage">
      Current stage: <strong>{{ activeStageLabel(prospect.stage) }}</strong>
    </p>
    <div v-if="!draft.editor" class="action-row">
      <Button
        v-for="action in stages"
        :key="action.target"
        :label="
          action.direction === 'backward'
            ? `Move back to ${activeStageLabel(action.target)}`
            : `Move to ${activeStageLabel(action.target)}`
        "
        severity="secondary"
        :disabled="disabled"
        @click="beginStage(action)"
      />
      <Button
        v-if="canClose"
        label="Close prospect"
        severity="secondary"
        :disabled="disabled"
        @click="closeForm"
      />
      <Button
        v-if="isReopening"
        label="Reopen to last active stage"
        severity="secondary"
        :disabled="disabled"
        @click="reopen"
      />
      <Button
        label="Record proposal draft"
        severity="secondary"
        :disabled="disabled"
        @click="beginProposalDraft"
      />
    </div>
    <form v-if="selectedAction" class="editor" @submit.prevent="submitStage">
      <h3>
        {{ selectedAction.direction === 'backward' ? 'Move stage backward' : 'Change stage' }}
      </h3>
      <p>
        Move from {{ activeStageLabel(prospect.stage) }} to
        {{ activeStageLabel(selectedAction.target) }}.
      </p>
      <label :for="occurredAtId">When did this stage change happen?</label>
      <input
        :id="occurredAtId"
        v-model="draft.occurredAt"
        type="datetime-local"
        required
        :disabled="disabled"
      />
      <p class="field-help">The activity record will also show when it was entered.</p>
      <label v-if="selectedAction.requiresReason" :for="reasonId">Reason for moving backward</label>
      <textarea
        v-if="selectedAction.requiresReason"
        :id="reasonId"
        v-model="draft.reason"
        rows="3"
        required
        :disabled="disabled"
      />
      <div class="action-row">
        <Button
          label="Save stage change"
          type="submit"
          :disabled="disabled || (selectedAction.requiresReason && !draft.reason.trim())"
        />
        <Button
          label="Cancel"
          type="button"
          severity="secondary"
          :disabled="disabled"
          @click="cancelStage"
        />
      </div>
    </form>
    <form v-else-if="draft.editor === 'close'" class="editor" @submit.prevent="submitClose">
      <h3>Close prospect</h3>
      <label :for="occurredAtId">When was the prospect closed?</label>
      <input
        :id="occurredAtId"
        v-model="draft.occurredAt"
        type="datetime-local"
        required
        :disabled="disabled"
      />
      <label :for="reasonId">Reason for closing</label>
      <textarea :id="reasonId" v-model="draft.reason" rows="3" required :disabled="disabled" />
      <div class="action-row">
        <Button label="Confirm close" type="submit" :disabled="disabled || !draft.reason.trim()" />
        <Button
          label="Cancel"
          type="button"
          severity="secondary"
          :disabled="disabled"
          @click="cancelStage"
        />
      </div>
    </form>
    <form
      v-else-if="draft.editor === 'proposal_draft'"
      class="editor"
      @submit.prevent="saveProposalDraft"
    >
      <h3>Record a proposal draft</h3>
      <p>Records a draft in history. It does not change the prospect stage or send a message.</p>
      <label :for="reasonId">Draft summary</label>
      <textarea
        :id="reasonId"
        v-model="draft.proposalSummary"
        rows="3"
        required
        :disabled="disabled"
      />
      <div class="action-row">
        <Button
          label="Record proposal draft"
          type="submit"
          :disabled="disabled || !draft.proposalSummary.trim()"
        />
        <Button
          label="Cancel"
          type="button"
          severity="secondary"
          :disabled="disabled"
          @click="cancelStage"
        />
      </div>
    </form>
  </section>
</template>

<style scoped>
.lifecycle-actions,
.editor {
  display: grid;
  gap: var(--space-2);
}
h2,
h3,
p {
  margin-top: 0;
}
h2 {
  margin-bottom: var(--space-1);
  font-size: 1.1rem;
}
h3 {
  margin-bottom: 0;
  font-size: 1rem;
}
p {
  margin-bottom: 0;
}
.current-stage {
  color: var(--color-text-muted);
}
.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.editor {
  border-left: 2px solid var(--color-border);
  padding-left: var(--space-3);
}
textarea,
input[type='datetime-local'] {
  width: 100%;
  min-height: 5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  padding: var(--space-2);
  background: var(--color-surface);
  color: var(--color-text);
  resize: vertical;
}
.field-help {
  color: var(--color-text-muted);
  font-size: 0.9rem;
}
</style>
