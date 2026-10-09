import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';

export type CompanyOption = components['schemas']['CompanyOptionResponse'];
export type CompanyOptionPage = components['schemas']['PageResponse_CompanyOptionResponse_'];

export function listCompanyOptions(
  search: string,
  offset = 0,
  limit = 50,
  signal?: AbortSignal,
): Promise<CompanyOptionPage> {
  const query = new URLSearchParams({
    search,
    offset: String(Math.max(0, Math.floor(offset))),
    limit: String(Math.min(100, Math.max(1, Math.floor(limit)))),
  });
  return apiRequest(`/api/v1/configuration-options/companies?${query}`, signal ? { signal } : {});
}
