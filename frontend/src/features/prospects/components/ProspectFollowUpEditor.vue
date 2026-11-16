<script setup lang="ts">
import { computed, useId } from 'vue';
import Button from 'primevue/button';
import type { ProspectView } from '../models/prospect';
import type {
  ProspectCommandSubmission,
  ProspectCommandDraft,
} from '../models/prospectCommandDraft';
import { cancelProspectDraft, startProspectDraft } from '../models/prospectCommandDraft';
import { followUpStatus } from '../models/followUpStatus';
import { useProspectClock } from '../composables/useProspectClock';

const props = defineProps<{
  prospect: ProspectView;
  draft: ProspectCommandDraft;
  disabled: boolean;
}>();
const emit = defineEmits<{ command: [submission: ProspectCommandSubmission] }>();
const draft = computed(() => props.draft);
const inputId = useId();
const editing = computed(() => draft.value.editor === 'follow_up');
const now = useProspectClock();
const reminderStatus = computed(() => followUpStatus(props.prospect.follow_up_at, now.value));
function toLocalInput(value: string): string {
  const date = new Date(value);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}
function begin(): void {
  if (props.disabled) return;
  startProspectDraft(draft.value, props.prospect.version);
  draft.value.editor = 'follow_up';
  draft.value.followUpAt = props.prospect.follow_up_at
    ? toLocalInput(props.prospect.follow_up_at)
    : '';
}
function cancel(): void {
  if (props.disabled) return;
  cancelProspectDraft(draft.value);
}
function occurredAt(): string {
  return new Date().toISOString();
}
function save(): void {
  const expectedVersion = draft.value.expectedVersion;
  if (props.disabled || expectedVersion === null || !draft.value.followUpAt) return;
  emit('command', {
    kind: 'follow_up',
    request: {
      expected_version: expectedVersion,
      occurred_at: occurredAt(),
      follow_up_at: new Date(draft.value.followUpAt).toISOString(),
      request_key: crypto.randomUUID(),
    },
  });
}
function clear(): void {
  const expectedVersion = draft.value.expectedVersion;
  if (props.disabled || expectedVersion === null) return;
  emit('command', {
    kind: 'clear_follow_up',
    request: {
      expected_version: expectedVersion,
      occurred_at: occurredAt(),
      request_key: crypto.randomUUID(),
    },
  });
}
function beginClear(): void {
  if (props.disabled) return;
  startProspectDraft(draft.value, props.prospect.version);
  clear();
}
</script>

<template>
  <section class="follow-up" aria-labelledby="follow-up-heading">
    <div class="heading-row">
      <div>
        <h2 id="follow-up-heading">Follow-up reminder</h2>
        <p>This is a reminder only. Huginn will not contact the Company.</p>
      </div>
      <div v-if="!editing" class="actions">
        <Button label="Set reminder" severity="secondary" :disabled="disabled" @click="begin" />
        <Button
          v-if="prospect.follow_up_at"
          label="Clear reminder"
          severity="secondary"
          :disabled="disabled"
          @click="beginClear"
        />
      </div>
    </div>
    <p v-if="prospect.follow_up_at && !editing" class="reminder-status">
      <strong>{{ reminderStatus === 'due' ? 'Due' : 'Upcoming' }}:</strong>
      Remind me {{ new Date(prospect.follow_up_at).toLocaleString() }}
    </p>
    <p v-else-if="!editing">No reminder is set.</p>
    <form v-if="editing" class="editor" @submit.prevent="save">
      <label :for="inputId">Reminder date and time</label>
      <input
        :id="inputId"
        v-model="draft.followUpAt"
        type="datetime-local"
        required
        :disabled="disabled"
      />
      <div class="actions">
        <Button label="Save reminder" type="submit" :disabled="disabled || !draft.followUpAt" />
        <Button
          label="Cancel"
          type="button"
          severity="secondary"
          :disabled="disabled"
          @click="cancel"
        />
      </div>
    </form>
  </section>
</template>

<style scoped>
.follow-up,
.editor {
  display: grid;
  gap: var(--space-2);
}
.heading-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
h2,
p {
  margin-top: 0;
}
h2 {
  margin-bottom: var(--space-1);
  font-size: 1.1rem;
}
.heading-row p {
  margin-bottom: 0;
  color: var(--color-text-muted);
}
.reminder-status strong {
  color: var(--color-text);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
input {
  min-height: 42px;
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
}
</style>
