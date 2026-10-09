import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';
export function listDiscoveryStrategies(
  offset = 0,
  limit = 100,
  active?: boolean,
  signal?: AbortSignal,
): Promise<components['schemas']['PageResponse_DiscoveryStrategyResponse_']> {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (active !== undefined) params.set('active', String(active));
  return apiRequest(`/api/v1/discovery-strategies?${params}`, signal ? { signal } : {});
}
