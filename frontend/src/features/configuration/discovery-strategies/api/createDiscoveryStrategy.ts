import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';
export function createDiscoveryStrategy(
  body: components['schemas']['DiscoveryStrategyCreateRequest'],
): Promise<components['schemas']['DiscoveryStrategyResponse']> {
  return apiRequest('/api/v1/discovery-strategies', { method: 'POST', body });
}
