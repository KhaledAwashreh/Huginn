import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';

export type UpdateAccountRequest = components['schemas']['UserUpdateRequest'];
export type UpdateAccountResponse = components['schemas']['UserResponse'];

export const updateAccount = (request: UpdateAccountRequest): Promise<UpdateAccountResponse> =>
  apiRequest('/api/v1/me', { method: 'PATCH', body: request });
