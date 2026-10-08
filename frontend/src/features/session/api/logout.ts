import { apiRequest } from '../../../api/client';

export const logout = (): Promise<void> =>
  apiRequest('/api/v1/sessions/current', { method: 'DELETE' });
