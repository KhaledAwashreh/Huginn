<script setup lang="ts">
import { computed, useId } from 'vue';
import Button from 'primevue/button';
import type { components } from '../../../api/generated/schema';
import type { ProspectView } from '../models/prospect';
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
const notesId = useId();
const editing = computed(() => draft.value.editor === 'notes');

function begin(): void {
  if (props.disabled) return;
  startProspectDraft(draft.value, props.prospect.version);
  draft.value.editor = 'notes';
  draft.value.notes = props.prospect.notes;
}
function cancel(): void {
  if (props.disabled) return;
  cancelProspectDraft(draft.value);
}
function save(): void {
  const expectedVersion = draft.value.expectedVersion;
  if (props.disabled || expectedVersion === null || draft.value.notes === props.prospect.notes)
    return;
  const request: components['schemas']['UpdateProspectNotesRequest'] = {
    expected_version: expectedVersion,
    occurred_at: new Date().toISOString(),
    replacement_notes: draft.value.notes,
    request_key: crypto.randomUUID(),
  };
  emit('command', { kind: 'notes', request });
}
</script>

<template>
  <section class="notes-editor" aria-labelledby="prospect-notes-heading">
    <div class="heading-row">
      <div>
        <h2 id="prospect-notes-heading">Notes</h2>
        <p>One editable memo. Replacing or clearing it keeps the prior text in activity history.</p>
      </div>
      <Button
        v-if="!editing"
        label="Edit notes"
        severity="secondary"
        :disabled="disabled"
        @click="begin"
      />
    </div>
    <form v-if="editing" class="editor" @submit.prevent="save">
      <label :for="notesId">Prospect notes</label>
      <textarea :id="notesId" v-model="draft.notes" rows="5" :disabled="disabled" />
      <div class="actions">
        <Button
          label="Save notes"
          type="submit"
          :disabled="disabled || draft.notes === prospect.notes"
        />
        <Button
          label="Cancel"
          type="button"
          severity="secondary"
          :disabled="disabled"
          @click="cancel"
        />
      </div>
    </form>
    <p v-else class="memo">{{ prospect.notes || 'No notes yet.' }}</p>
  </section>
</template>

<style scoped>
.notes-editor,
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
textarea {
  width: 100%;
  min-height: 7rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  padding: var(--space-2);
  background: var(--color-surface);
  color: var(--color-text);
  resize: vertical;
}
.memo {
  margin-bottom: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
</style>
