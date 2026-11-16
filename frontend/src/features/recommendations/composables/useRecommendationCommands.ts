import { computed, ref, watch } from 'vue';
import { useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { laterRecommendation } from '../api/laterRecommendation';
import { markRecommendationNotRelevant } from '../api/markRecommendationNotRelevant';
import { saveRecommendation } from '../api/saveRecommendation';
import type {
  RecommendationCommandDraft,
  RecommendationCommandIntent,
} from '../models/recommendationCommandDraft';

function sendDecision(intent: RecommendationCommandIntent): Promise<unknown> {
  switch (intent.kind) {
    case 'saved':
      return saveRecommendation(intent.recommendationId, intent.request);
    case 'not_relevant':
      return markRecommendationNotRelevant(intent.recommendationId, intent.request);
    case 'later':
      return laterRecommendation(intent.recommendationId, intent.request);
  }
}

export function useRecommendationCommands(identity: Readonly<{ value: string }>) {
  const client = useQueryClient();
  const pending = ref(false);
  const error = ref('');
  const outcome = ref<'idle' | 'uncertain' | 'stale'>('idle');
  const canRetry = computed(() => outcome.value === 'uncertain');
  const needsRefresh = computed(() => outcome.value === 'stale');
  let retryAction: (() => Promise<unknown>) | null = null;
  let identityGeneration = 0;

  watch(
    identity,
    () => {
      identityGeneration += 1;
      pending.value = false;
      error.value = '';
      outcome.value = 'idle';
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
    outcome.value = 'idle';
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
        outcome.value = 'stale';
        retryAction = null;
      } else if (caught instanceof ApiError && caught.status < 500) {
        error.value =
          caught.status === 422
            ? 'The decision could not be accepted. Review the form and try again.'
            : 'The decision was not accepted. Refresh the current state before trying again.';
        retryAction = null;
      } else {
        error.value = 'We could not confirm the result. Retry the same update safely.';
        retryAction = action;
        outcome.value = 'uncertain';
      }
      return undefined;
    } finally {
      if (identityGeneration === commandGeneration) pending.value = false;
    }
  }

  async function executeDecision(
    intent: RecommendationCommandIntent,
    draft: RecommendationCommandDraft,
    complete: (result: unknown) => void,
    isCurrent: () => boolean,
  ): Promise<void> {
    if (pending.value || intent.identity !== identity.value || !isCurrent()) return;
    draft.intent = intent;
    draft.status = 'pending';
    draft.error = '';
    await execute(
      () => sendDecision(intent),
      (result) => {
        if (intent.identity === identity.value && isCurrent()) complete(result);
      },
    );
    if (intent.identity !== identity.value || !isCurrent() || draft.status !== 'pending') return;
    draft.error = error.value;
    draft.status = canRetry.value ? 'uncertain' : needsRefresh.value ? 'stale' : 'editing';
    if (draft.status === 'editing') draft.intent = null;
  }

  async function retry(): Promise<unknown | undefined> {
    if (!canRetry.value || !retryAction) return undefined;
    return execute(retryAction);
  }

  async function refresh(): Promise<void> {
    const refreshIdentity = identity.value;
    const refreshGeneration = identityGeneration;
    retryAction = null;
    outcome.value = 'idle';
    error.value = '';
    await invalidate(refreshIdentity);
    if (identity.value !== refreshIdentity || identityGeneration !== refreshGeneration) return;
  }

  function clearError(): void {
    if (canRetry.value) return;
    error.value = '';
  }

  return {
    pending,
    error,
    canRetry,
    needsRefresh,
    execute,
    executeDecision,
    retry,
    refresh,
    clearError,
  };
}
