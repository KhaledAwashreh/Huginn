import { describe, expect, it } from 'vitest';
import { ApiError } from '@/api/apiError';
import { queryClient } from '@/app/queryClient';
import { matchesQueryKey } from '@/features/matches/composables/useMatches';

describe('matches query behavior', () => {
  it('scopes keys to both signed-in account and user', () => {
    expect(matchesQueryKey('account-a', 'user-a', 40)).toEqual([
      'matches',
      'account-a',
      'user-a',
      'list',
      40,
    ]);
    expect(matchesQueryKey('account-a', 'user-b', 40)).not.toEqual(
      matchesQueryKey('account-a', 'user-a', 40),
    );
  });

  it('does not automatically retry terminal 401, 403, 404, or 422 reads', async () => {
    expect(queryClient.getDefaultOptions().queries?.retry).toBe(false);
    for (const status of [401, 403, 404, 422]) {
      let calls = 0;
      await expect(
        queryClient.fetchQuery({
          queryKey: ['matches-terminal-error', status, Math.random()],
          queryFn: () => {
            calls++;
            throw new ApiError(status, 'request_failed', 'Request failed');
          },
        }),
      ).rejects.toBeInstanceOf(ApiError);
      expect(calls).toBe(1);
    }
  });
});
