import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export const getAccountSecurity = (
  signal?: AbortSignal,
): Promise<components['schemas']['AccountSecurityResponse']> =>
  apiRequest('/api/v1/me/account-security', signal ? { signal } : {});
