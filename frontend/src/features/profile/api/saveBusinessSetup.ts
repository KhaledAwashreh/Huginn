import { apiRequest } from '../../../api/client';
import type { BusinessSetup, BusinessSetupRequest } from '../models/businessSetup';

export const saveBusinessSetup = (body: BusinessSetupRequest): Promise<BusinessSetup> =>
  apiRequest('/api/v1/me/business/setup', { method: 'PUT', body });
