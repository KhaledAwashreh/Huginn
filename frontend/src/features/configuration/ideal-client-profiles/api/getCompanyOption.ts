import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';

export type CompanyOption = components['schemas']['CompanyOptionResponse'];

export function getCompanyOption(id: string, signal?: AbortSignal): Promise<CompanyOption> {
  return apiRequest(
    `/api/v1/configuration-options/companies/${encodeURIComponent(id)}`,
    signal ? { signal } : {},
  );
}
