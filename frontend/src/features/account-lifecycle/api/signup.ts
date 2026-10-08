import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export const signup = (
  body: components['schemas']['SignupRequest'],
): Promise<components['schemas']['LifecycleReceiptResponse']> =>
  apiRequest('/api/v1/accounts', { method: 'POST', body, anonymous: true });
