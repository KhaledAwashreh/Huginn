import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';
export function updateDiscoveryStrategy(
  id: string,
  body: components['schemas']['DiscoveryStrategyUpdateRequest'],
): Promise<components['schemas']['DiscoveryStrategyResponse']> {
  return apiRequest(`/api/v1/discovery-strategies/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body,
  });
}
