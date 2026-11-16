import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function recordProposalDraft(
  prospectId: string,
  request: components['schemas']['RecordProposalDraftRequest'],
): Promise<components['schemas']['ProspectCommandResponse']> {
  return apiRequest(`/api/v1/prospects/${encodeURIComponent(prospectId)}/proposal-drafts`, {
    method: 'POST',
    body: request,
  });
}
