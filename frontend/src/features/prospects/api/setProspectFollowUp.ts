import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function setProspectFollowUp(
  prospectId: string,
  request: components['schemas']['SetProspectFollowUpRequest'],
): Promise<components['schemas']['ProspectCommandResponse']> {
  return apiRequest(`/api/v1/prospects/${encodeURIComponent(prospectId)}/follow-up`, {
    method: 'POST',
    body: request,
  });
}
