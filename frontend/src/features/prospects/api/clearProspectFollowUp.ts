import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function clearProspectFollowUp(
  prospectId: string,
  request: components['schemas']['ClearProspectFollowUpRequest'],
): Promise<components['schemas']['ProspectCommandResponse']> {
  return apiRequest(`/api/v1/prospects/${encodeURIComponent(prospectId)}/clear-follow-up`, {
    method: 'POST',
    body: request,
  });
}
