import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export const resetPassword = (body: components['schemas']['ResetPasswordRequest']): Promise<void> =>
  apiRequest('/api/v1/password-resets/complete', { method: 'POST', body, anonymous: true });
