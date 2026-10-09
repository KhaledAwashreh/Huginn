import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';

export type ChangePasswordRequest = components['schemas']['PasswordChangeRequest'];

export const changePassword = (request: ChangePasswordRequest): Promise<void> =>
  apiRequest('/api/v1/me/password', { method: 'PATCH', body: request });
