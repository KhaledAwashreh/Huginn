import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';
export function getDiscoveryStrategy(
  id: string,
  signal?: AbortSignal,
): Promise<components['schemas']['DiscoveryStrategyResponse']> {
  return apiRequest(
    `/api/v1/discovery-strategies/${encodeURIComponent(id)}`,
    signal ? { signal } : {},
  );
}
