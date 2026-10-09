import { apiRequest } from '../../../../api/client';
export function deleteDiscoveryStrategy(id: string): Promise<void> {
  return apiRequest(`/api/v1/discovery-strategies/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
