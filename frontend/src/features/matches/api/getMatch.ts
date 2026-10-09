import { apiRequest } from '../../../api/client';
import type { UserMatch } from './listMatches';

export function getMatch(id: string, signal?: AbortSignal) {
  return apiRequest<UserMatch>(
    `/api/v1/matches/${encodeURIComponent(id)}`,
    signal ? { signal } : {},
  );
}
