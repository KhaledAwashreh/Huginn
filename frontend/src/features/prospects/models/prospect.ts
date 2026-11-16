import type { components } from '../../../api/generated/schema';

export type ProspectView = components['schemas']['ProspectResponse'];
export type ProspectSummary = components['schemas']['ProspectSummaryResponse'];
export type ProspectPage = components['schemas']['PageResponse_ProspectResponse_'];
export type ProspectActivity = components['schemas']['ProspectActivityResponse'];
export type ProspectStage = ProspectView['stage'];
export type ActiveProspectStage = Exclude<ProspectStage, 'closed'>;

const activeStages: readonly ActiveProspectStage[] = [
  'saved',
  'contacted',
  'in_conversation',
  'proposal_sent',
];
const forwardStage: Partial<Record<ActiveProspectStage, ProspectStage>> = {
  saved: 'contacted',
  contacted: 'in_conversation',
  in_conversation: 'proposal_sent',
  proposal_sent: 'won_client',
};
const backwardStage: Partial<Record<ProspectStage, ActiveProspectStage>> = {
  contacted: 'saved',
  in_conversation: 'contacted',
  proposal_sent: 'in_conversation',
  won_client: 'proposal_sent',
};

export type ProspectStageAction = {
  target: ProspectStage;
  direction: 'forward' | 'backward';
  requiresReason: boolean;
};

export function prospectStageActions(stage: ProspectStage): ProspectStageAction[] {
  if (stage === 'closed') return [];
  const actions: ProspectStageAction[] = [];
  const forward = forwardStage[stage];
  if (forward) actions.push({ target: forward, direction: 'forward', requiresReason: false });
  const backward = backwardStage[stage];
  if (backward) actions.push({ target: backward, direction: 'backward', requiresReason: true });
  return actions;
}

export function activeStageLabel(stage: string): string {
  if (activeStages.includes(stage as ActiveProspectStage)) return stage.replaceAll('_', ' ');
  if (stage === 'won_client') return 'won client';
  if (stage === 'closed') return 'closed';
  return 'Unknown stage';
}
