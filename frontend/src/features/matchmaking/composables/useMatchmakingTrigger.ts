import { computed, ref } from 'vue';
import { useMutation } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { triggerMatchmakingRun } from '../api/triggerMatchmakingRun';
import type { MatchmakingTriggerDraft } from '../forms/matchmakingTriggerDraft';
import { serializeMatchmakingTrigger } from '../forms/serializeMatchmakingTrigger';

export function useMatchmakingTrigger() {
  const requestId = ref<string>();
  const pendingBody = ref<ReturnType<typeof serializeMatchmakingTrigger>>();
  const uncertain = ref(false);
  const activeRunId = ref<string>();
  const mutation = useMutation({
    mutationFn: (body: ReturnType<typeof serializeMatchmakingTrigger>) =>
      triggerMatchmakingRun(body),
    retry: false,
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        const activeReference = error.details.find(
          (item) => typeof item.active_matching_run_id === 'string',
        );
        activeRunId.value =
          typeof activeReference?.active_matching_run_id === 'string'
            ? activeReference.active_matching_run_id
            : undefined;
        uncertain.value = false;
      } else if (!(error instanceof ApiError) || error.status >= 500) {
        uncertain.value = true;
      }
    },
    onSuccess: () => {
      uncertain.value = false;
      activeRunId.value = undefined;
    },
  });
  const hasUnresolvedOutcome = computed(
    () =>
      uncertain.value ||
      (mutation.error.value instanceof ApiError && mutation.error.value.status === 409),
  );

  async function submit(draft: MatchmakingTriggerDraft) {
    if (mutation.isPending.value || hasUnresolvedOutcome.value) return undefined;
    const nextRequestId = crypto.randomUUID();
    const body = serializeMatchmakingTrigger(draft, nextRequestId);
    requestId.value = nextRequestId;
    pendingBody.value = body;
    const receipt = await mutation.mutateAsync(body);
    requestId.value = undefined;
    pendingBody.value = undefined;
    return receipt;
  }

  async function retrySameRequest() {
    if (!uncertain.value || !pendingBody.value || mutation.isPending.value) return undefined;
    const receipt = await mutation.mutateAsync(pendingBody.value);
    requestId.value = undefined;
    pendingBody.value = undefined;
    return receipt;
  }

  function resolvePriorOutcome(): void {
    if (mutation.isPending.value) return;
    requestId.value = undefined;
    pendingBody.value = undefined;
    uncertain.value = false;
    activeRunId.value = undefined;
    mutation.reset();
  }

  return {
    mutation,
    requestId,
    pendingBody,
    uncertain,
    activeRunId,
    hasUnresolvedOutcome,
    submit,
    retrySameRequest,
    resolvePriorOutcome,
  };
}
