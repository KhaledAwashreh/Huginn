import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import PrimeVue from 'primevue/config';
import App from '../../src/app/App.vue';
import { queryClient } from '../../src/app/queryClient';
import ResetPasswordPage from '../../src/features/account-lifecycle/pages/ResetPasswordPage.vue';
import { useSession } from '../../src/features/session/composables/useSession';

const identity = {
  account_id: 'account-1',
  user_id: 'user-1',
  csrf_token: 'session-csrf',
  expires_at: '2099-01-01T00:00:00Z',
};

async function prepareSession(): Promise<void> {
  vi.stubGlobal('fetch', (url: string) => {
    if (url === '/api/v1/sessions/current') return Promise.resolve(Response.json(identity));
    return Promise.resolve(new Response(null, { status: 204 }));
  });
  await useSession().bootstrap();
  queryClient.setQueryData(['account-1', 'private'], { email: 'private@example.test' });
}

function resetPage() {
  window.history.replaceState({}, '', '/reset-password#token=reset-proof');
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/reset-password', component: ResetPasswordPage }],
  });
  return router
    .push('/reset-password')
    .then(() => mount(ResetPasswordPage, { global: { plugins: [router, PrimeVue] } }));
}

afterEach(() => {
  useSession().clear();
  queryClient.clear();
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
});

it('clears the authenticated session and private cache after a successful password reset', async () => {
  await prepareSession();
  const wrapper = await resetPage();
  await wrapper.get('#reset-password').setValue('ResetNow!12345');
  await wrapper.get('form').trigger('submit');
  await flushPromises();

  expect(wrapper.text()).toContain('Password saved');
  expect(useSession().context.value).toBeNull();
  expect(queryClient.getQueryData(['account-1', 'private'])).toBeUndefined();
});

it('keeps the existing session and private cache when password reset fails', async () => {
  await prepareSession();
  vi.stubGlobal('fetch', (url: string) =>
    url === '/api/v1/password-resets/complete'
      ? Promise.resolve(Response.json({}, { status: 500 }))
      : Promise.resolve(Response.json(identity)),
  );
  const wrapper = await resetPage();
  await wrapper.get('#reset-password').setValue('ResetNow!12345');
  await wrapper.get('form').trigger('submit');
  await flushPromises();

  expect(wrapper.text()).toContain('The service is unavailable. Try again.');
  expect(useSession().context.value?.account_id).toBe('account-1');
  expect(queryClient.getQueryData(['account-1', 'private'])).toEqual({
    email: 'private@example.test',
  });
});

it('renders authenticated public routes outside the workspace shell', async () => {
  await prepareSession();
  const publicPage = { template: '<main><h1>Public page</h1></main>' };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/public', component: publicPage, meta: { requiresAuth: false } },
      {
        path: '/private',
        component: { template: '<div>Private page</div>' },
        meta: { requiresAuth: true },
      },
      { path: '/login', component: { template: '<main><h1>Sign in</h1></main>' }, name: 'login' },
    ],
  });
  await router.push('/public');
  const wrapper = mount(App, { global: { plugins: [router] } });

  expect(wrapper.findAll('main')).toHaveLength(1);
  expect(wrapper.find('.app-shell').exists()).toBe(false);

  await router.push('/private');
  await flushPromises();
  expect(wrapper.findAll('main')).toHaveLength(1);
  expect(wrapper.find('.app-shell').exists()).toBe(true);
});
