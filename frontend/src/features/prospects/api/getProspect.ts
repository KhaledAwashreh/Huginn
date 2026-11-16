import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export function getProspect(
  prospectId: string,
  signal?: AbortSignal,
): Promise<components['schemas']['ProspectResponse']> {
  const path = `/api/v1/prospects/${encodeURIComponent(prospectId)}`;
  return apiRequest(path, signal ? { signal } : {});
}
