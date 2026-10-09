import { describe, expect, it } from 'vitest';
import { ApiError } from '@/api/apiError';
import { queryClient } from '@/app/queryClient';
import { ref } from 'vue';
import { applyMatchStatus, matchesQueryKey } from '@/features/matches/composables/useMatches';

describe('matches query behavior', () => {
  it('scopes keys to both signed-in account and user and resets pages when status changes', () => {
    expect(matchesQueryKey('account-a', 'user-a', undefined, 40)).toEqual([
      'matches',
      'account-a',
      'user-a',
      'list',
      null,
      40,
    ]);
    expect(matchesQueryKey('account-a', 'user-a', 'new', 0)).not.toEqual(
      matchesQueryKey('account-a', 'user-a', undefined, 0),
    );
    const status = ref<'new' | undefined>('new');
    const offset = ref(40);
    applyMatchStatus(status, offset, undefined);
    expect(status.value).toBeUndefined();
    expect(offset.value).toBe(0);
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
