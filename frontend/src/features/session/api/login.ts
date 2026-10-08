import { apiRequest } from '../../../api/client';
import type { LoginDraft } from '../forms/loginDraft';
import type { components } from '../../../api/generated/schema';

export const login = (draft: LoginDraft): Promise<components['schemas']['LoginResponse']> =>
  apiRequest('/api/v1/sessions', { method: 'POST', body: draft, anonymous: true });
