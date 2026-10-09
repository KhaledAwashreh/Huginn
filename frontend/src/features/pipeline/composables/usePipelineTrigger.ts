import { computed, ref } from 'vue';
import { useMutation } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { triggerInvocation } from '../api/triggerInvocation';

export function usePipelineTrigger() {
  const requestId = ref<string>();
  const uncertain = ref(false);
  const conflictId = ref<string>();
  const trigger = useMutation({
    mutationFn: (id: string) => triggerInvocation(id),
    retry: false,
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        const reference = error.details.find(
          (item) => typeof item.active_invocation_id === 'string',
        );
        conflictId.value =
          typeof reference?.active_invocation_id === 'string'
            ? reference.active_invocation_id
            : undefined;
        uncertain.value = false;
      } else if (!(error instanceof ApiError) || error.status >= 500) {
        uncertain.value = true;
      }
    },
    onSuccess: () => {
      uncertain.value = false;
      conflictId.value = undefined;
    },
  });
  const conflict = computed(
    () => trigger.error.value instanceof ApiError && trigger.error.value.status === 409,
  );

  function newRequestId(): string {
    return crypto.randomUUID();
  }

  async function start(): Promise<void> {
    if (trigger.isPending.value || uncertain.value || conflict.value) return;
    requestId.value = newRequestId();
    uncertain.value = false;
    conflictId.value = undefined;
    await trigger.mutateAsync(requestId.value);
    requestId.value = undefined;
  }

  async function retryUncertain(): Promise<void> {
    if (!requestId.value || trigger.isPending.value) return;
    await trigger.mutateAsync(requestId.value);
    requestId.value = undefined;
  }

  function resolvePriorOutcome(): void {
    if (trigger.isPending.value) return;
    requestId.value = undefined;
    uncertain.value = false;
    conflictId.value = undefined;
    trigger.reset();
  }

  return {
    trigger,
    requestId,
    uncertain,
    conflict,
    conflictId,
    start,
    retryUncertain,
    resolvePriorOutcome,
  };
}
