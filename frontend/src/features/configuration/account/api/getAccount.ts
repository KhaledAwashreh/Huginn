import { apiRequest } from '../../../../api/client';
import type { components } from '../../../../api/generated/schema';

export type GetAccountResponse = components['schemas']['UserResponse'];

export const getAccount = (signal?: AbortSignal): Promise<GetAccountResponse> =>
  apiRequest('/api/v1/me', signal ? { signal } : {});
