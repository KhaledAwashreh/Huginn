import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';

export function saveSingleDiscoveryConfiguration(
  body: components['schemas']['SingleDiscoveryConfigurationRequest'],
): Promise<components['schemas']['DiscoveryStrategyResponse']> {
  return apiRequest('/api/v1/discovery-strategies/single-configuration', { method: 'PUT', body });
}
