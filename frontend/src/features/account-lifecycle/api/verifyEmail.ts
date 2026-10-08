import { apiRequest } from '../../../api/client';
import type { components } from '../../../api/generated/schema';

export const verifyEmail = (body: components['schemas']['VerifyEmailRequest']): Promise<void> =>
  apiRequest('/api/v1/email-verifications', { method: 'POST', body, anonymous: true });
