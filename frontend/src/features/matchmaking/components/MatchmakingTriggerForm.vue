<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import TargetUserSelect from './TargetUserSelect.vue';
import SignalWindowFields from './SignalWindowFields.vue';
import { useMatchmakingTrigger } from '../composables/useMatchmakingTrigger';
import type { MatchmakingTriggerDraft } from '../forms/matchmakingTriggerDraft';
import { createMatchmakingTriggerDraft } from '../forms/matchmakingTriggerDraft';
import type { components } from '../../../api/generated/schema';
const router = useRouter();
type TargetUser = components['schemas']['TargetUserResponse'];
const draft = reactive<MatchmakingTriggerDraft>(createMatchmakingTriggerDraft());
const selectedUser = computed({
  get: () => draft.selectedUser ?? undefined,
  set: (value: TargetUser | undefined) => {
    draft.selectedUser = value ?? null;
  },
});
const trigger = useMatchmakingTrigger();
const validationError = ref('');
const canSubmit = computed(
  () =>
    !trigger.mutation.isPending.value &&
    !trigger.hasUnresolvedOutcome.value &&
    (draft.targetKind === 'all_eligible' || !!draft.selectedUser),
);
async function submit() {
  validationError.value = '';
  try {
    const receipt = await trigger.submit(draft);
    if (receipt) await router.push({ name: 'admin-matchmaking-run', params: { id: receipt.id } });
  } catch (error) {
    validationError.value =
      error instanceof Error ? error.message : 'The request outcome needs review.';
  }
}
async function retrySame() {
  try {
    const receipt = await trigger.retrySameRequest();
    if (receipt) await router.push({ name: 'admin-matchmaking-run', params: { id: receipt.id } });
  } catch {
    validationError.value =
      'The same request is still unresolved. Review history before making another run.';
  }
}
function updateDraft(next: MatchmakingTriggerDraft) {
  Object.assign(draft, next);
}
</script>

<template>
  <form class="trigger-card" @submit.prevent="submit">
    <h2>Start a matchmaking run</h2>
    <p>
      Each run evaluates the selected users against their current active strategies for this signal
      window.
    </p>
    <fieldset :disabled="trigger.hasUnresolvedOutcome.value || trigger.mutation.isPending.value">
      <legend>Target</legend>
      <label
        ><input v-model="draft.targetKind" type="radio" value="user" /> One selected user</label
      >
      <label
        ><input v-model="draft.targetKind" type="radio" value="all_eligible" /> All currently
        eligible users</label
      >
      <TargetUserSelect v-if="draft.targetKind === 'user'" v-model="selectedUser" />
      <SignalWindowFields :model-value="draft" @update:model-value="updateDraft" />
    </fieldset>
    <p v-if="validationError" role="alert">{{ validationError }}</p>
    <p v-if="trigger.uncertain.value" role="status">
      The server may have accepted this request. Do not start another run until you resolve this
      request ID: {{ trigger.requestId.value }}.
    </p>
    <p v-if="trigger.activeRunId.value">
      A matchmaking run is already active.
      <RouterLink :to="{ name: 'admin-matchmaking-run', params: { id: trigger.activeRunId.value } }"
        >Open the active run</RouterLink
      >.
    </p>
    <p v-if="trigger.requestId.value && trigger.uncertain.value">
      Request ID: <code>{{ trigger.requestId.value }}</code>
    </p>
    <details v-if="trigger.uncertain.value && trigger.pendingBody.value">
      <summary>Review the exact request retained for retry</summary>
      <pre>{{ JSON.stringify(trigger.pendingBody.value, null, 2) }}</pre>
    </details>
    <div class="actions">
      <Button
        type="submit"
        :label="trigger.mutation.isPending.value ? 'Submitting…' : 'Start run'"
        :disabled="!canSubmit"
      />
      <Button
        v-if="trigger.uncertain.value"
        type="button"
        label="Retry this exact request"
        severity="secondary"
        :disabled="trigger.mutation.isPending.value"
        @click="retrySame"
      />
      <Button
        v-if="trigger.hasUnresolvedOutcome.value"
        type="button"
        label="I reviewed history; allow a new request"
        severity="secondary"
        :disabled="trigger.mutation.isPending.value"
        @click="trigger.resolvePriorOutcome"
      />
    </div>
  </form>
</template>

<style scoped>
.trigger-card {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
.trigger-card > fieldset {
  display: grid;
  gap: var(--space-3);
  border: 0;
  padding: 0;
}
.trigger-card > fieldset > label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 32px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}
</style>
