import { computed, ref, shallowRef, watch, type Ref } from 'vue';
import { useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { changeProspectStage } from '../api/changeProspectStage';
import { clearProspectFollowUp } from '../api/clearProspectFollowUp';
import { closeProspect } from '../api/closeProspect';
import { correctProspectActivityTime } from '../api/correctProspectActivityTime';
import { recordProposalDraft } from '../api/recordProposalDraft';
import { reopenProspect } from '../api/reopenProspect';
import { setProspectFollowUp } from '../api/setProspectFollowUp';
import { updateProspectNotes } from '../api/updateProspectNotes';
import {
  captureProspectCommand,
  resetProspectDraft,
  type ProspectCommandDraft,
  type ProspectCommandIntent,
  type ProspectCommandKind,
  type ProspectCommandRequestByKind,
  type ProspectCommandSubmission,
} from '../models/prospectCommandDraft';

async function send(intent: ProspectCommandIntent): Promise<unknown> {
  switch (intent.kind) {
    case 'stage':
      return changeProspectStage(intent.prospectId, intent.request);
    case 'close':
      return closeProspect(intent.prospectId, intent.request);
    case 'reopen':
      return reopenProspect(intent.prospectId, intent.request);
    case 'notes':
      return updateProspectNotes(intent.prospectId, intent.request);
    case 'follow_up':
      return setProspectFollowUp(intent.prospectId, intent.request);
    case 'clear_follow_up':
      return clearProspectFollowUp(intent.prospectId, intent.request);
    case 'proposal_draft':
      return recordProposalDraft(intent.prospectId, intent.request);
    case 'correct_activity_time':
      return correctProspectActivityTime(intent.prospectId, intent.request);
  }
}

export function useProspectCommands(identity: Readonly<Ref<string>>) {
  const queryClient = useQueryClient();
  const pending = ref(false);
  const activeDraft = shallowRef<ProspectCommandDraft | null>(null);
  const error = computed(() => activeDraft.value?.error ?? '');
  const canRetry = computed(() => activeDraft.value?.status === 'uncertain');
  const needsRefresh = computed(
    () => activeDraft.value?.status === 'stale' && Boolean(error.value),
  );
  const message = ref('');
  const messageProspectId = ref<string | null>(null);
  let generation = 0;

  watch(
    identity,
    () => {
      generation += 1;
      pending.value = false;
      activeDraft.value = null;
      message.value = '';
      messageProspectId.value = null;
    },
    { flush: 'sync' },
  );

  async function invalidate(targetIdentity: string, prospectId: string): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['prospects', targetIdentity, 'list'] }),
      queryClient.invalidateQueries({
        queryKey: ['prospects', targetIdentity, 'detail', prospectId],
      }),
    ]);
  }

  async function executeIntent(intent: ProspectCommandIntent, draft: ProspectCommandDraft) {
    if (pending.value || identity.value !== intent.identity) return false;
    const requestGeneration = generation;
    pending.value = true;
    activeDraft.value = draft;
    draft.error = '';
    message.value = '';
    messageProspectId.value = null;
    draft.status = 'pending';
    draft.intent = intent;
    try {
      await send(intent);
      if (identity.value !== intent.identity || generation !== requestGeneration) return false;
      resetProspectDraft(draft);
      message.value = 'Saved. Current prospect details and history are refreshing.';
      messageProspectId.value = intent.prospectId;
      await invalidate(intent.identity, intent.prospectId);
      return identity.value === intent.identity && generation === requestGeneration;
    } catch (caught) {
      if (identity.value !== intent.identity || generation !== requestGeneration) return false;
      if (caught instanceof ApiError && caught.status === 409) {
        draft.error =
          'This prospect changed. Refresh its details, then discard or reopen this draft.';
        draft.status = 'stale';
        draft.intent = null;
      } else if (caught instanceof ApiError && caught.status < 500) {
        draft.error = 'The update was not accepted. Review your changes and try again.';
        draft.status = 'error';
        draft.intent = null;
      } else {
        draft.error = 'We could not confirm the result. Retry the same update safely.';
        draft.status = 'uncertain';
        draft.intent = intent;
      }
      return false;
    } finally {
      if (generation === requestGeneration) pending.value = false;
    }
  }

  async function execute<K extends ProspectCommandKind>(
    draft: ProspectCommandDraft,
    kind: K,
    request: ProspectCommandRequestByKind[K],
  ): Promise<boolean> {
    const intent = captureProspectCommand(draft, identity.value, kind, request);
    return executeIntent(intent, draft);
  }

  async function submit(
    draft: ProspectCommandDraft,
    submission: ProspectCommandSubmission,
  ): Promise<boolean> {
    switch (submission.kind) {
      case 'stage':
        return execute(draft, 'stage', submission.request);
      case 'close':
        return execute(draft, 'close', submission.request);
      case 'reopen':
        return execute(draft, 'reopen', submission.request);
      case 'notes':
        return execute(draft, 'notes', submission.request);
      case 'follow_up':
        return execute(draft, 'follow_up', submission.request);
      case 'clear_follow_up':
        return execute(draft, 'clear_follow_up', submission.request);
      case 'proposal_draft':
        return execute(draft, 'proposal_draft', submission.request);
      case 'correct_activity_time':
        return execute(draft, 'correct_activity_time', submission.request);
    }
  }

  async function retry(draft: ProspectCommandDraft): Promise<boolean> {
    const intent = draft.intent;
    if (
      pending.value ||
      draft.status !== 'uncertain' ||
      !intent ||
      intent.identity !== identity.value
    )
      return false;
    return executeIntent(intent, draft);
  }

  async function refresh(prospectId: string): Promise<void> {
    const requestedIdentity = identity.value;
    const requestGeneration = generation;
    if (activeDraft.value) activeDraft.value.error = '';
    message.value = '';
    messageProspectId.value = null;
    await invalidate(requestedIdentity, prospectId);
    if (identity.value !== requestedIdentity || generation !== requestGeneration) return;
  }

  return {
    pending,
    error,
    canRetry,
    needsRefresh,
    message,
    messageProspectId,
    execute,
    submit,
    retry,
    refresh,
  };
}
