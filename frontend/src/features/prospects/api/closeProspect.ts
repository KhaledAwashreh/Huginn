import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function closeProspect(
  prospectId: string,
  request: components['schemas']['CloseProspectRequest'],
): Promise<components['schemas']['ProspectCommandResponse']> {
  return apiRequest(`/api/v1/prospects/${encodeURIComponent(prospectId)}/close`, {
    method: 'POST',
    body: request,
  });
}
