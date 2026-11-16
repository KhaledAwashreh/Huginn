import type { ProspectActivity } from './prospect';

const labels: Record<ProspectActivity['kind'], string> = {
  prospect_saved: 'Saved as prospect',
  stage_changed: 'Stage changed',
  closed: 'Closed',
  reopened: 'Reopened',
  note_added: 'Notes updated',
  follow_up_set: 'Follow-up reminder set',
  follow_up_cleared: 'Follow-up reminder cleared',
  proposal_drafted: 'Proposal draft recorded',
  proposal_sent: 'Proposal sent',
  correction: 'Activity time corrected',
};

export function orderProspectActivities(
  activities: readonly ProspectActivity[],
): ProspectActivity[] {
  return activities
    .map((activity, index) => ({ activity, index }))
    .sort(
      (left, right) =>
        left.activity.recorded_at.localeCompare(right.activity.recorded_at) ||
        correctionOrder(left.activity) - correctionOrder(right.activity) ||
        left.index - right.index,
    )
    .map(({ activity }) => activity);
}

function correctionOrder(activity: ProspectActivity): number {
  if (activity.kind !== 'correction') return 0;
  const sequence = activity.payload.correction_sequence;
  return typeof sequence === 'number' ? sequence : 0;
}

export function canCorrectActivityTime(activity: ProspectActivity): boolean {
  return activity.kind !== 'correction' && activity.correction_of_id === null;
}

export function activityLabel(kind: string): string {
  return Object.hasOwn(labels, kind)
    ? labels[kind as ProspectActivity['kind']]
    : 'Other recorded activity';
}

export function activitySummary(activity: ProspectActivity): string {
  const payload = activity.payload;
  if (activity.kind === 'stage_changed') {
    const before = payload.prior_stage;
    const after = payload.new_stage;
    const stages =
      typeof before === 'string' && typeof after === 'string'
        ? `${before.replaceAll('_', ' ')} → ${after.replaceAll('_', ' ')}`
        : '';
    const reason = payload.reason;
    return [stages, typeof reason === 'string' && reason.trim() ? reason : '']
      .filter(Boolean)
      .join('. ');
  }
  if (activity.kind === 'closed' && typeof payload.reason === 'string') return payload.reason;
  if (activity.kind === 'note_added') {
    const prior = payload.prior;
    const replacement = payload.replacement;
    return `Notes changed from “${typeof prior === 'string' && prior ? prior : 'empty'}” to “${typeof replacement === 'string' && replacement ? replacement : 'empty'}”`;
  }
  if (activity.kind === 'follow_up_set' || activity.kind === 'follow_up_cleared') {
    const prior = payload.prior;
    const replacement = payload.replacement;
    return `Reminder changed from ${typeof prior === 'string' ? prior : 'none'} to ${typeof replacement === 'string' ? replacement : 'none'}`;
  }
  if (activity.kind === 'correction') {
    const prior = payload.prior;
    const replacement = payload.replacement;
    if (typeof prior === 'string' && typeof replacement === 'string') {
      const sequence = payload.correction_sequence;
      return `Correction ${typeof sequence === 'number' ? sequence : 1}: occurred time changed from ${prior} to ${replacement}`;
    }
  }
  if (activity.kind === 'proposal_drafted' && typeof payload.summary === 'string')
    return payload.summary;
  return '';
}
