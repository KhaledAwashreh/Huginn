import { apiRequest } from '../../../api/client';
import type { BusinessSetup } from '../models/businessSetup';

export const getBusinessSetup = (signal?: AbortSignal): Promise<BusinessSetup> =>
  apiRequest('/api/v1/me/business/setup', signal ? { signal } : {});
