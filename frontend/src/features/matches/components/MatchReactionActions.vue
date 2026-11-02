<script setup lang="ts">
import { computed, ref, useId } from 'vue';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import Select from 'primevue/select';
import Textarea from 'primevue/textarea';
import { ThumbsDown, ThumbsUp } from '@lucide/vue';
import type { FeedbackReason } from '../../recommendations/models/recommendationFeedback';
import { awaitingBackendAttrs } from '../../../shared/availability/awaitingBackend';
import { useMatchReactions } from '../composables/useMatchReactions';
import { MATCH_REJECTION_REASONS } from '../lib/matchRejectionReasons';

const props = defineProps<{ match: { id: string; company: { name: string } } }>();
const { reactionFor, markGood, markNotAFit, clearReaction } = useMatchReactions();
const id = useId();
const reaction = computed(() => reactionFor(props.match.id));
const dialogVisible = ref(false);
const reason = ref<FeedbackReason | null>(null);
const note = ref('');

function toggleUp(): void {
  if (reaction.value?.kind === 'up') clearReaction(props.match.id);
  else markGood(props.match);
}
function toggleDown(): void {
  if (reaction.value?.kind === 'down') {
    clearReaction(props.match.id);
    return;
  }
  reason.value = null;
  note.value = '';
  dialogVisible.value = true;
}
function submit(): void {
  if (!reason.value) return;
  markNotAFit(props.match, reason.value, note.value);
  dialogVisible.value = false;
}
</script>

<template>
  <div class="match-reactions">
    <button
      v-bind="awaitingBackendAttrs"
      type="button"
      :class="['reaction', { 'reaction--up': reaction?.kind === 'up' }]"
      :aria-label="`Good match: ${match.company.name}`"
      :aria-pressed="reaction?.kind === 'up'"
      @click="toggleUp"
    >
      <ThumbsUp :size="18" aria-hidden="true" />
    </button>
    <button
      v-bind="awaitingBackendAttrs"
      type="button"
      :class="['reaction', { 'reaction--down': reaction?.kind === 'down' }]"
      :aria-label="`Not a fit: ${match.company.name}`"
      :aria-pressed="reaction?.kind === 'down'"
      @click="toggleDown"
    >
      <ThumbsDown :size="18" aria-hidden="true" />
    </button>
    <Dialog
      v-model:visible="dialogVisible"
      modal
      :draggable="false"
      :header="`Why isn't ${match.company.name} a fit?`"
      :style="{ width: 'min(28rem, calc(100vw - 2rem))' }"
    >
      <form class="rejection-form" @submit.prevent="submit">
        <span :id="`${id}-reason`" class="field-label">Reason</span>
        <Select
          v-model="reason"
          :aria-labelledby="`${id}-reason`"
          :options="MATCH_REJECTION_REASONS"
          option-label="label"
          option-value="value"
          placeholder="Choose a reason"
        />
        <label :for="`${id}-note`">Anything to add? (optional)</label>
        <Textarea :id="`${id}-note`" v-model="note" rows="3" />
        <div class="rejection-actions">
          <Button
            type="button"
            label="Cancel"
            severity="secondary"
            @click="dialogVisible = false"
          />
          <Button type="submit" label="Save feedback" :disabled="!reason" />
        </div>
      </form>
    </Dialog>
  </div>
</template>

<style scoped>
.match-reactions {
  display: flex;
  gap: var(--space-1);
}
.reaction {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text-muted);
  cursor: pointer;
}
.reaction:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.reaction:not(:disabled):hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}
.reaction--up {
  border-color: var(--color-success-border);
  background: var(--color-success-surface);
  color: var(--color-success-text);
}
.reaction--down {
  border-color: var(--color-danger-border);
  background: var(--color-danger-surface);
  color: var(--color-danger-text);
}
.rejection-form {
  display: grid;
  gap: var(--space-2);
}
.rejection-form label,
.field-label {
  font-weight: 600;
}
.rejection-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
</style>
