import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';

export type ConfigurationOption = components['schemas']['ConfigurationOptionResponse'];
export type ConfigurationOptions = components['schemas']['ConfigurationOptionsResponse'];

export function getConfigurationOptions(signal?: AbortSignal): Promise<ConfigurationOptions> {
  return apiRequest('/api/v1/configuration-options', signal ? { signal } : {});
}
