import { afterEach, expect, it, vi } from 'vitest';
import { useSession } from '../../src/features/session/composables/useSession';
import { queryClient } from '../../src/app/queryClient';
import { validateReturnPath } from '../../src/shared/navigation/validateReturnPath';
import { apiRequest } from '../../src/api/client';

it.each([401, 200])(
  'rejects late %s responses after same-account credential replacement',
  async (status) => {
    const session = useSession();
    const identity = {
      account_id: 'account',
      user_id: 'user',
      csrf_token: 'old-proof',
      expires_at: '2099-01-01T00:00:00Z',
    };
    vi.stubGlobal('fetch', () => Promise.resolve(Response.json(identity)));
    await session.bootstrap();
    let finish: ((response: Response) => void) | undefined;
    vi.stubGlobal(
      'fetch',
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    const oldRead = apiRequest('/api/v1/me');
    const rejected = expect(oldRead).rejects.toThrow();
    vi.stubGlobal('fetch', () =>
      Promise.resolve(Response.json({ ...identity, csrf_token: 'new-proof' })),
    );
    await session.bootstrap();
    finish?.(Response.json({ old: 'private' }, { status }));
    await rejected;
    expect(session.context.value?.csrf_token).toBe('new-proof');
  },
);

afterEach(() => {
  useSession().clear();
  vi.unstubAllGlobals();
});

it('removes previous identity data when bootstrap observes an account switch', async () => {
  const session = useSession();
  const first = {
    account_id: 'first',
    user_id: 'user-one',
    csrf_token: 'proof-one',
    expires_at: '2099-01-01T00:00:00Z',
  };
  vi.stubGlobal('fetch', () => Promise.resolve(Response.json(first)));
  await session.bootstrap();
  queryClient.setQueryData(['first', 'offerings'], ['private-first']);
  vi.stubGlobal('fetch', () =>
    Promise.resolve(Response.json({ ...first, account_id: 'second', user_id: 'user-two' })),
  );
  await session.bootstrap();
  expect(session.context.value?.account_id).toBe('second');
  expect(queryClient.getQueryData(['first', 'offerings'])).toBeUndefined();
});

it('clears identity, query data and CSRF after session expiry', async () => {
  const session = useSession();
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      Response.json({
        account_id: 'first',
        user_id: 'user-one',
        csrf_token: 'proof',
        expires_at: '2099-01-01T00:00:00Z',
      }),
    ),
  );
  await session.bootstrap();
  queryClient.setQueryData(['first', 'icps'], ['private']);
  vi.stubGlobal('fetch', () => Promise.resolve(Response.json({}, { status: 401 })));
  await session.bootstrap();
  expect(session.context.value).toBeNull();
  expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
});

it('allows local returns while rejecting scheme, protocol-relative and encoded redirects', () => {
  expect(validateReturnPath('/account?tab=profile')).toBe('/account?tab=profile');
  for (const value of [
    '//evil.test',
    'https://evil.test',
    '/\\evil.test',
    '/%2f%2fevil.test',
    '/login',
    '/%5cevil.test',
  ]) {
    expect(validateReturnPath(value)).toBe('/');
  }
});

it('a stale bootstrap response cannot erase a newly logged-in identity', async () => {
  const session = useSession();
  let resolveOld: ((response: Response) => void) | undefined;
  let firstBootstrap = true;
  vi.stubGlobal('fetch', (path: string) => {
    if (path === '/api/v1/sessions/current' && firstBootstrap) {
      firstBootstrap = false;
      return new Promise<Response>((resolve) => {
        resolveOld = resolve;
      });
    }
    return Promise.resolve(
      Response.json({
        account_id: 'new-account',
        user_id: 'new-user',
        csrf_token: 'new-proof',
        expires_at: '2099-01-01T00:00:00Z',
      }),
    );
  });
  const previous = session.bootstrap();
  session.clear();
  const login = session.login({ username: 'new-user', password: 'new-password' });
  await Promise.resolve();
  await Promise.resolve();
  resolveOld?.(Response.json({}, { status: 401 }));
  await Promise.allSettled([previous, login]);
  expect(session.context.value?.account_id).toBe('new-account');
});

it('admin demotion clears admin caches while retaining the signed-in workspace', async () => {
  const session = useSession();
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      Response.json({
        account_id: 'admin-account',
        user_id: 'owner',
        role: 'admin',
        csrf_token: 'proof',
        expires_at: '2099-01-01T00:00:00Z',
      }),
    ),
  );
  await session.bootstrap();
  queryClient.setQueryData(['admin', 'pipeline', 'admin-account'], ['private-history']);
  queryClient.setQueryData(['owner', 'offerings'], ['retained-draft-source']);
  vi.stubGlobal('fetch', () => Promise.resolve(Response.json({}, { status: 403 })));
  await expect(apiRequest('/api/v1/admin/pipeline/invocations')).rejects.toThrow();
  expect(session.isAdministrator.value).toBe(false);
  expect(session.isAuthenticated.value).toBe(true);
  expect(session.context.value?.csrf_token).toBe('proof');
  expect(queryClient.getQueryData(['admin', 'pipeline', 'admin-account'])).toBeUndefined();
  expect(queryClient.getQueryData(['owner', 'offerings'])).toEqual(['retained-draft-source']);
});
