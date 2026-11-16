import type { components } from '../../../api/generated/schema';
import type { ProspectView } from './prospect';

export type ProspectCommandKind =
  | 'stage'
  | 'close'
  | 'reopen'
  | 'notes'
  | 'follow_up'
  | 'clear_follow_up'
  | 'proposal_draft'
  | 'correct_activity_time';

export interface ProspectCommandRequestByKind {
  stage: components['schemas']['ChangeProspectStageRequest'];
  close: components['schemas']['CloseProspectRequest'];
  reopen: components['schemas']['ReopenProspectRequest'];
  notes: components['schemas']['UpdateProspectNotesRequest'];
  follow_up: components['schemas']['SetProspectFollowUpRequest'];
  clear_follow_up: components['schemas']['ClearProspectFollowUpRequest'];
  proposal_draft: components['schemas']['RecordProposalDraftRequest'];
  correct_activity_time: components['schemas']['CorrectProspectActivityTimeRequest'];
}

export type ProspectCommandIntent = {
  [K in ProspectCommandKind]: {
    identity: string;
    prospectId: string;
    kind: K;
    request: Readonly<ProspectCommandRequestByKind[K]>;
  };
}[ProspectCommandKind];

export type ProspectCommandSubmission = {
  [K in ProspectCommandKind]: {
    kind: K;
    request: ProspectCommandRequestByKind[K];
  };
}[ProspectCommandKind];

export interface ProspectCommandDraft {
  prospectId: string;
  snapshot: ProspectView | null;
  expectedVersion: number | null;
  editing: boolean;
  status: 'idle' | 'pending' | 'uncertain' | 'stale' | 'error';
  error: string;
  intent: ProspectCommandIntent | null;
  editor: 'stage' | 'close' | 'proposal_draft' | 'notes' | 'follow_up' | 'correction' | null;
  stageTarget: ProspectView['stage'] | null;
  reason: string;
  occurredAt: string;
  notes: string;
  followUpAt: string;
  proposalSummary: string;
  correctionActivityId: string;
  correctionHeadId: string | null;
  replacementOccurredAt: string;
}

export function createProspectCommandDraft(prospectId: string): ProspectCommandDraft {
  return {
    prospectId,
    snapshot: null,
    expectedVersion: null,
    editing: false,
    status: 'idle',
    error: '',
    intent: null,
    editor: null,
    stageTarget: null,
    reason: '',
    occurredAt: '',
    notes: '',
    followUpAt: '',
    proposalSummary: '',
    correctionActivityId: '',
    correctionHeadId: null,
    replacementOccurredAt: '',
  };
}

export function startProspectDraft(draft: ProspectCommandDraft, version: number): void {
  if (draft.expectedVersion !== null) return;
  draft.expectedVersion = version;
  draft.editing = true;
}

export function cancelProspectDraft(draft: ProspectCommandDraft): void {
  if (draft.status === 'pending' || draft.status === 'uncertain' || draft.status === 'stale')
    return;
  draft.expectedVersion = null;
  draft.editing = false;
  draft.status = 'idle';
  draft.error = '';
  draft.intent = null;
  draft.editor = null;
  draft.stageTarget = null;
  draft.reason = '';
  draft.occurredAt = '';
  draft.notes = draft.snapshot?.notes ?? '';
  draft.followUpAt = '';
  draft.proposalSummary = '';
  draft.correctionActivityId = '';
  draft.correctionHeadId = null;
  draft.replacementOccurredAt = '';
}

export function captureProspectCommand<K extends ProspectCommandKind>(
  draft: ProspectCommandDraft,
  identity: string,
  kind: K,
  request: ProspectCommandRequestByKind[K],
): Extract<ProspectCommandIntent, { kind: K }> {
  const captured = Object.freeze(structuredClone(request));
  const intent = Object.freeze({
    identity,
    prospectId: draft.prospectId,
    kind,
    request: captured,
  }) as unknown as Extract<ProspectCommandIntent, { kind: K }>;
  draft.intent = intent;
  draft.status = 'pending';
  draft.error = '';
  return intent;
}

export function hasProspectDraft(draft: ProspectCommandDraft): boolean {
  return Boolean(
    draft.intent ||
    draft.status !== 'idle' ||
    draft.expectedVersion !== null ||
    draft.editing ||
    draft.reason.trim() ||
    draft.occurredAt ||
    draft.stageTarget ||
    draft.editor ||
    draft.notes !== (draft.snapshot?.notes ?? '') ||
    draft.followUpAt ||
    draft.proposalSummary.trim() ||
    draft.correctionActivityId ||
    draft.replacementOccurredAt,
  );
}
