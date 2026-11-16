import { expect, it, vi } from 'vitest';
import { getBusinessProfile } from '@/features/profile/api/getBusinessProfile';
import { updateBusinessProfile } from '@/features/profile/api/updateBusinessProfile';

const state = vi.hoisted(() => ({ apiRequest: vi.fn() }));

vi.mock('@/api/client', () => ({ apiRequest: state.apiRequest }));

it('loads the session-resolved Business without an owner path parameter', async () => {
  state.apiRequest.mockResolvedValueOnce({ id: 'business-1' });
  const signal = new AbortController().signal;

  await getBusinessProfile(signal);

  expect(state.apiRequest).toHaveBeenCalledWith('/api/v1/me/business', { signal });
});

it('patches only the explicit Business changes without an owner field', async () => {
  state.apiRequest.mockResolvedValueOnce({ id: 'business-1' });
  const request = { description: 'A Business description.' };

  await updateBusinessProfile(request);

  expect(state.apiRequest).toHaveBeenCalledWith('/api/v1/me/business', {
    method: 'PATCH',
    body: request,
  });
});
