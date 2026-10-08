import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export const enrollRecoveryEmail = (): Promise<components['schemas']['LifecycleReceiptResponse']> =>
  apiRequest('/api/v1/me/recovery-email-verifications', {
    method: 'POST',
    body: {} satisfies components['schemas']['EnrollRecoveryEmailRequest'],
  });
