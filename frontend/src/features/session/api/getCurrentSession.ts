import { apiRequest } from '../../../api/client';
import type { SessionContext } from '../sessionContext';

export const getCurrentSession = (signal: AbortSignal): Promise<SessionContext> =>
  apiRequest('/api/v1/sessions/current', { signal });
