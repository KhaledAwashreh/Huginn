<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import { ApiError } from '../../../api/apiError';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import { usePipelineTrigger } from '../composables/usePipelineTrigger';

const router = useRouter();
const action = usePipelineTrigger();
withDefaults(defineProps<{ canTrigger?: boolean }>(), { canTrigger: true });
const errorMessage = computed(() => {
  const error = action.trigger.error.value;
  if (error instanceof ApiError && error.status === 409)
    return 'Another collection run is already active. Open it from history before starting another run.';
  if (action.uncertain.value)
    return 'The response was not received, so the run outcome is unknown. Check history before deciding what to do.';
  return error instanceof Error ? error.message : 'The collection run could not be started.';
});

async function start(): Promise<void> {
  try {
    await action.start();
    const receipt = action.trigger.data.value;
    if (receipt) await router.push(`/admin/pipeline/invocations/${receipt.id}`);
  } catch {
    // The action state presents the safe outcome and an explicit recovery choice.
  }
}

async function retry(): Promise<void> {
  try {
    await action.retryUncertain();
    const receipt = action.trigger.data.value;
    if (receipt) await router.push(`/admin/pipeline/invocations/${receipt.id}`);
  } catch {
    // Keep the same request ID available for a deliberate retry.
  }
}
</script>

<template>
  <div class="run-action">
    <Button
      label="Pull data"
      :loading="action.trigger.isPending.value"
      :disabled="
        !canTrigger ||
        action.trigger.isPending.value ||
        action.uncertain.value ||
        action.conflict.value
      "
      @click="start"
    />
    <p v-if="!canTrigger" class="history-required">
      Load the unfiltered first history page before starting a run.
    </p>
    <ErrorState v-if="action.trigger.isError.value" :message="errorMessage">
      <RouterLink
        v-if="action.conflictId.value"
        :to="`/admin/pipeline/invocations/${action.conflictId.value}`"
        >Open active invocation</RouterLink
      >
      <RouterLink to="/admin/pipeline">Check history</RouterLink>
      <Button
        v-if="action.uncertain.value"
        label="Retry same request"
        severity="secondary"
        :disabled="action.trigger.isPending.value"
        @click="retry"
      />
      <Button
        v-if="action.uncertain.value || action.conflict.value"
        label="I reviewed history; prepare a new run"
        severity="secondary"
        :disabled="action.trigger.isPending.value"
        @click="action.resolvePriorOutcome"
      />
    </ErrorState>
  </div>
</template>

<style scoped>
.run-action {
  display: grid;
  justify-items: start;
  gap: var(--space-3);
}
.history-required {
  margin: 0;
  color: var(--color-text-muted);
}
</style>
