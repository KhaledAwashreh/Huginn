import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function reopenProspect(
  prospectId: string,
  request: components['schemas']['ReopenProspectRequest'],
): Promise<components['schemas']['ProspectCommandResponse']> {
  return apiRequest(`/api/v1/prospects/${encodeURIComponent(prospectId)}/reopen`, {
    method: 'POST',
    body: request,
  });
}
