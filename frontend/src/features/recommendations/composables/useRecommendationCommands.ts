import { ref, watch } from 'vue';
import { useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';

export function useRecommendationCommands(identity: Readonly<{ value: string }>) {
  const client = useQueryClient();
  const pending = ref(false);
  const error = ref('');
  const canRetry = ref(false);
  const needsRefresh = ref(false);
  let retryAction: (() => Promise<unknown>) | null = null;
  let identityGeneration = 0;

  watch(
    identity,
    () => {
      identityGeneration += 1;
      pending.value = false;
      error.value = '';
      canRetry.value = false;
      needsRefresh.value = false;
      retryAction = null;
    },
    { flush: 'sync' },
  );

  async function invalidate(targetIdentity = identity.value): Promise<void> {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['prospecting', targetIdentity, 'recommendations'] }),
      client.invalidateQueries({ queryKey: ['prospecting', targetIdentity, 'suppressions'] }),
      client.invalidateQueries({ queryKey: ['prospecting', targetIdentity, 'preferences'] }),
    ]);
  }

  async function execute(
    action: () => Promise<unknown>,
    onSuccess?: (result: unknown) => void,
  ): Promise<unknown | undefined> {
    if (pending.value) return undefined;
    const commandIdentity = identity.value;
    const commandGeneration = identityGeneration;
    pending.value = true;
    error.value = '';
    canRetry.value = false;
    needsRefresh.value = false;
    try {
      const result = await action();
      if (identity.value !== commandIdentity || identityGeneration !== commandGeneration)
        return undefined;
      retryAction = null;
      onSuccess?.(result);
      if (identity.value === commandIdentity) await invalidate(commandIdentity);
      return result;
    } catch (caught) {
      if (identity.value !== commandIdentity || identityGeneration !== commandGeneration)
        return undefined;
      if (caught instanceof ApiError && caught.status === 409) {
        error.value = 'This recommendation changed. Refresh its current state before trying again.';
        needsRefresh.value = true;
        retryAction = null;
      } else if (caught instanceof ApiError && caught.status < 500) {
        error.value =
          caught.status === 422
            ? 'The decision could not be accepted. Review the form and try again.'
            : 'The decision was not accepted. Refresh the current state before trying again.';
        retryAction = null;
      } else {
        error.value = 'The result is uncertain. Retry the exact same request to check its receipt.';
        retryAction = action;
        canRetry.value = true;
      }
      return undefined;
    } finally {
      if (identityGeneration === commandGeneration) pending.value = false;
    }
  }

  async function retry(): Promise<unknown | undefined> {
    if (!canRetry.value || !retryAction) return undefined;
    return execute(retryAction);
  }

  async function refresh(): Promise<void> {
    const refreshIdentity = identity.value;
    const refreshGeneration = identityGeneration;
    retryAction = null;
    canRetry.value = false;
    needsRefresh.value = false;
    error.value = '';
    await invalidate(refreshIdentity);
    if (identity.value !== refreshIdentity || identityGeneration !== refreshGeneration) return;
  }

  function clearError(): void {
    if (canRetry.value) return;
    error.value = '';
  }

  return { pending, error, canRetry, needsRefresh, execute, retry, refresh, clearError };
}
