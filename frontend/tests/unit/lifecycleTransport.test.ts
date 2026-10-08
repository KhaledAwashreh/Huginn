import { afterEach, expect, it, vi } from 'vitest';
import { apiRequest, configureApiClient } from '../../src/api/client';

afterEach(() => {
  configureApiClient({});
  vi.unstubAllGlobals();
});

it('rejects anonymous mutation exemptions outside the public lifecycle contract', async () => {
  configureApiClient({});
  const fetch = vi.fn<typeof globalThis.fetch>(() =>
    Promise.resolve(new Response(null, { status: 204 })),
  );
  vi.stubGlobal('fetch', fetch);
  await expect(
    apiRequest('/api/v1/me/password', { method: 'PATCH', body: {}, anonymous: true }),
  ).rejects.toThrow();
  expect(fetch).not.toHaveBeenCalled();
});

it.each([
  '/api/v1/accounts',
  '/api/v1/email-verifications',
  '/api/v1/email-verifications/resend',
  '/api/v1/password-resets',
  '/api/v1/password-resets/complete',
])('permits public POST to %s without session CSRF', async (path) => {
  configureApiClient({});
  const fetch = vi.fn<typeof globalThis.fetch>(() =>
    Promise.resolve(new Response(null, { status: 204 })),
  );
  vi.stubGlobal('fetch', fetch);
  await apiRequest(path, { method: 'POST', body: {}, anonymous: true });
  const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
  expect(new Headers(init?.headers).has('X-CSRF-Token')).toBe(false);
  expect(init?.credentials).toBe('same-origin');
});
