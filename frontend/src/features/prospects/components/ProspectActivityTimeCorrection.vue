<script setup lang="ts">
import { computed, useId } from 'vue';
import Button from 'primevue/button';
import type { components } from '../../../api/generated/schema';
import { canCorrectActivityTime } from '../models/prospectActivityTimeline';
import type { ProspectActivity } from '../models/prospect';
import type { ProspectCommandDraft } from '../models/prospectCommandDraft';
import { cancelProspectDraft, startProspectDraft } from '../models/prospectCommandDraft';

const props = defineProps<{
  activity: ProspectActivity;
  prospectVersion: number;
  draft: ProspectCommandDraft;
  disabled: boolean;
}>();
const emit = defineEmits<{
  command: [request: components['schemas']['CorrectProspectActivityTimeRequest']];
}>();
const draft = computed(() => props.draft);
const fieldId = useId();
const isEditing = computed(() => draft.value.correctionActivityId === props.activity.id);
const correctionAvailable = computed(
  () => draft.value.editor === null || (draft.value.editor === 'correction' && isEditing.value),
);
function localDateTime(value: string): string {
  const date = new Date(value);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}
function isoDateTime(value: string): string {
  return new Date(value).toISOString();
}
function begin(): void {
  if (!canCorrectActivityTime(props.activity) || props.disabled || !correctionAvailable.value)
    return;
  startProspectDraft(draft.value, props.prospectVersion);
  draft.value.correctionActivityId = props.activity.id;
  draft.value.editor = 'correction';
  draft.value.correctionHeadId = props.activity.correction_head_id;
  draft.value.replacementOccurredAt = localDateTime(props.activity.effective_occurred_at);
}
function cancel(): void {
  if (draft.value.status === 'pending' || draft.value.status === 'uncertain') return;
  cancelProspectDraft(draft.value);
}
function submit(): void {
  const expectedVersion = draft.value.expectedVersion;
  if (
    !isEditing.value ||
    expectedVersion === null ||
    !draft.value.replacementOccurredAt ||
    props.disabled
  )
    return;
  emit('command', {
    expected_version: expectedVersion,
    expected_correction_head_id: draft.value.correctionHeadId,
    original_activity_id: props.activity.id,
    replacement_occurred_at: isoDateTime(draft.value.replacementOccurredAt),
    request_key: crypto.randomUUID(),
  });
}
</script>

<template>
  <div v-if="canCorrectActivityTime(activity)" class="time-correction">
    <Button
      v-if="!isEditing"
      label="Correct occurrence time"
      severity="secondary"
      size="small"
      :disabled="disabled || !correctionAvailable"
      @click="begin"
    />
    <form v-else class="correction-form" @submit.prevent="submit">
      <label :for="fieldId">Corrected occurrence time</label>
      <input
        :id="fieldId"
        v-model="draft.replacementOccurredAt"
        type="datetime-local"
        required
        :disabled="disabled"
      />
      <p>The original activity remains in history. This adds a time correction.</p>
      <div class="actions">
        <Button label="Save time correction" type="submit" :disabled="disabled" />
        <Button
          label="Cancel correction"
          severity="secondary"
          :disabled="disabled"
          @click="cancel"
        />
      </div>
    </form>
  </div>
</template>

<style scoped>
.time-correction,
.correction-form {
  display: grid;
  gap: var(--space-2);
}
.correction-form {
  max-width: 32rem;
  border-left: 2px solid var(--color-border);
  padding: var(--space-2) 0 var(--space-2) var(--space-3);
}
.correction-form input {
  min-height: 42px;
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
}
.correction-form p {
  margin: 0;
  color: var(--color-text-muted);
}
.actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
</style>
