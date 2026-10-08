import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export const resendVerification = (body: {
  email: string;
}): Promise<components['schemas']['LifecycleReceiptResponse']> =>
  apiRequest('/api/v1/email-verifications/resend', { method: 'POST', body, anonymous: true });
