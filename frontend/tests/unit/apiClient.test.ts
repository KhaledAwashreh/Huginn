import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiRequest, configureApiClient } from '../../src/api/client';
import { ApiError } from '../../src/api/apiError';

afterEach(() => {
  vi.unstubAllGlobals();
  configureApiClient({});
});

describe('JSON transport', () => {
  it.each([
    [400, /Reload/],
    [401, /Sign in/],
    [404, /no longer available/],
    [409, /conflict/],
    [422, /Check/],
  ])(
    'replaces generic server feedback for status %s with recovery guidance',
    async (status, guidance) => {
      vi.stubGlobal('fetch', () =>
        Promise.resolve(
          Response.json(
            { error: { code: 'request_failed', message: 'Request could not be completed' } },
            { status: Number(status) },
          ),
        ),
      );
      await expect(apiRequest('/api/v1/me')).rejects.toMatchObject({
        message: expect.stringMatching(guidance as RegExp),
      });
    },
  );
  it.each([403, 429])(
    'keeps actionable status %s guidance with generic server envelopes',
    async (status) => {
      vi.stubGlobal('fetch', () =>
        Promise.resolve(
          Response.json(
            { error: { code: 'request_failed', message: 'Request could not be completed' } },
            { status },
          ),
        ),
      );
      await expect(apiRequest('/api/v1/me')).rejects.toMatchObject({
        message: expect.stringMatching(status === 403 ? /Reload/ : /Wait/),
      });
    },
  );
  it('sends only same-origin cookie requests and decodes empty success', async () => {
    let received: RequestInit | undefined;
    vi.stubGlobal('fetch', (_path: string, init: RequestInit) => {
      received = init;
      return Promise.resolve(new Response(null, { status: 204 }));
    });
    configureApiClient({ getCsrfToken: () => 'proof' });
    expect(await apiRequest('/api/v1/sessions/current', { method: 'DELETE' })).toBeUndefined();
    expect(received?.credentials).toBe('same-origin');
    expect(new Headers(received?.headers).get('X-CSRF-Token')).toBe('proof');
    await expect(apiRequest('https://external.test/')).rejects.toThrow();
    await expect(apiRequest('//external.test/')).rejects.toThrow();
  });

  it('preserves nested validation paths and does not replay failed mutations', async () => {
    let calls = 0;
    vi.stubGlobal('fetch', () => {
      calls++;
      return Promise.resolve(
        Response.json(
          { detail: [{ loc: ['body', 'experience', 0, 'start_date'], msg: 'Invalid month' }] },
          { status: 422 },
        ),
      );
    });
    configureApiClient({ getCsrfToken: () => 'proof' });
    try {
      await apiRequest('/api/v1/me', { method: 'PATCH', body: { first_name: 'Ada' } });
      expect.fail('expected validation failure');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).fields).toEqual([
        { path: ['experience', 0, 'start_date'], message: 'Invalid month' },
      ]);
    }
    expect(calls).toBe(1);
  });

  it('tears down identity only for 401, leaving 403 drafts and identity intact', async () => {
    let resets = 0;
    configureApiClient({
      onUnauthorized: () => {
        resets++;
      },
      getCsrfToken: () => 'proof',
    });
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        Response.json({ error: { code: 'forbidden', message: 'Forbidden' } }, { status: 403 }),
      ),
    );
    await expect(apiRequest('/api/v1/me', { method: 'PATCH' })).rejects.toMatchObject({
      status: 403,
    });
    expect(resets).toBe(0);
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        Response.json(
          { error: { code: 'authentication_required', message: 'Authentication required' } },
          { status: 401 },
        ),
      ),
    );
    await expect(apiRequest('/api/v1/me')).rejects.toMatchObject({ status: 401 });
    expect(resets).toBe(1);
  });

  it('hides unexpected server exceptions behind safe generic feedback', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        Response.json({ detail: 'postgresql://secret:password@host' }, { status: 500 }),
      ),
    );
    await expect(apiRequest('/api/v1/me')).rejects.toMatchObject({
      message: 'The service is unavailable. Try again.',
    });
  });
});
