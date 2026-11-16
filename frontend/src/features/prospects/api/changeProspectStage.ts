import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function changeProspectStage(
  prospectId: string,
  request: components['schemas']['ChangeProspectStageRequest'],
): Promise<components['schemas']['ProspectCommandResponse']> {
  return apiRequest(`/api/v1/prospects/${encodeURIComponent(prospectId)}/stage`, {
    method: 'POST',
    body: request,
  });
}
