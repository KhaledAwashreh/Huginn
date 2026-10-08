import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export const forgotPassword = (body: {
  email: string;
}): Promise<components['schemas']['LifecycleReceiptResponse']> =>
  apiRequest('/api/v1/password-resets', { method: 'POST', body, anonymous: true });
