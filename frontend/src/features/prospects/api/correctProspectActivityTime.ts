import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function correctProspectActivityTime(
  prospectId: string,
  request: components['schemas']['CorrectProspectActivityTimeRequest'],
): Promise<components['schemas']['ProspectCommandResponse']> {
  return apiRequest(
    `/api/v1/prospects/${encodeURIComponent(prospectId)}/activity-time-corrections`,
    { method: 'POST', body: request },
  );
}
