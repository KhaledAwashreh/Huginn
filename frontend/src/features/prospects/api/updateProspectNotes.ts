import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function updateProspectNotes(
  prospectId: string,
  request: components['schemas']['UpdateProspectNotesRequest'],
): Promise<components['schemas']['ProspectCommandResponse']> {
  return apiRequest(`/api/v1/prospects/${encodeURIComponent(prospectId)}/notes`, {
    method: 'POST',
    body: request,
  });
}
