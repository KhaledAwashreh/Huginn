import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export interface ListRecommendationsOptions {
  strategyId?: string;
  status: 'open' | 'converted' | 'rejected' | 'all' | undefined;
  search: string;
  offset: number;
  limit: number;
}

export function listRecommendations(
  { strategyId, status, search, offset, limit }: ListRecommendationsOptions,
  signal?: AbortSignal,
): Promise<components['schemas']['PageResponse_RecommendationResponse_']> {
  const query = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (strategyId) query.set('strategy_id', strategyId);
  if (status) query.set('status', status);
  if (search) query.set('search', search);
  return apiRequest(`/api/v1/recommendations?${query.toString()}`, signal ? { signal } : {});
}
