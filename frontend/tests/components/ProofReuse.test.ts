import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { flushPromises, mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { afterEach, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import type { Component } from 'vue';
import { configureApiClient } from '../../src/api/client';
import VerifyEmailPage from '../../src/features/account-lifecycle/pages/VerifyEmailPage.vue';
import ResetPasswordPage from '../../src/features/account-lifecycle/pages/ResetPasswordPage.vue';
import { useSession } from '../../src/features/session/composables/useSession';

const cases = [
  { route: '/verify-email', component: VerifyEmailPage, success: 'Email verified' },
  { route: '/reset-password', component: ResetPasswordPage, success: 'Password saved' },
];
const mounted: { unmount: () => void }[] = [];
const clients: QueryClient[] = [];

function openProof(route: string, token: string) {
  window.history.replaceState({}, '', `${route}#token=${token}`);
  window.dispatchEvent(new HashChangeEvent('hashchange'));
}

async function render(component: Component, route: string) {
  openProof(route, 'first-proof');
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: route, component },
      { path: '/login', component: { template: '<h1>Sign in</h1>' } },
      { path: '/forgot-password', component: { template: '<h1>Forgot password</h1>' } },
    ],
  });
  await router.push(route);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(queryClient);
  const wrapper = mount(component, {
    global: { plugins: [router, PrimeVue, [VueQueryPlugin, { queryClient }]] },
  });
  mounted.push(wrapper);
  return {
    wrapper,
    async submit() {
      if (route === '/reset-password') {
        await wrapper.get('#reset-password').setValue('Repeat!12345');
        await wrapper.get('form').trigger('submit');
      } else await wrapper.get('button').trigger('click');
    },
    control: () =>
      route === '/reset-password' ? wrapper.find('#reset-password') : wrapper.find('button'),
  };
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  for (const client of clients.splice(0)) client.clear();
  useSession().clear();
  configureApiClient({});
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
});

it.each(cases)(
  'requires a new explicit action when $route receives a proof after success',
  async ({ route, component, success }) => {
    const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(() =>
      Promise.resolve(new Response(null, { status: 204 })),
    );
    vi.stubGlobal('fetch', fetch);
    const view = await render(component, route);
    await view.submit();
    await flushPromises();
    expect(view.wrapper.text()).toContain(success);

    openProof(route, 'second-proof');
    await flushPromises();
    expect(view.wrapper.text()).not.toContain(success);
    expect(view.control().exists()).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(window.location.hash).toBe('');
    await view.submit();
    await flushPromises();
    expect(JSON.parse(fetch.mock.calls[1]?.[1]?.body as string).token).toBe('second-proof');
    expect(view.wrapper.text()).toContain(success);
  },
);

it.each(cases)(
  'replaces the previous $route success with guidance for a malformed new link',
  async ({ route, component, success }) => {
    const fetch = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
    vi.stubGlobal('fetch', fetch);
    const view = await render(component, route);
    await view.submit();
    await flushPromises();
    expect(view.wrapper.text()).toContain(success);

    openProof(route, 'first&token=duplicate');
    await flushPromises();
    expect(view.wrapper.text()).not.toContain(success);
    expect(view.wrapper.text()).toContain(
      route === '/verify-email' ? 'Open the link' : 'Open the original email link',
    );
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(window.location.hash).toBe('');
  },
);

it.each(cases.flatMap((entry) => [204, 422].map((status) => ({ ...entry, status }))))(
  'keeps the new $route proof when the previous pending request returns $status',
  async ({ route, component, success, status }) => {
    let finish: ((response: Response) => void) | undefined;
    let requests = 0;
    const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(() => {
      requests += 1;
      return requests === 1
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : Promise.resolve(new Response(null, { status: 204 }));
    });
    vi.stubGlobal('fetch', fetch);
    const view = await render(component, route);
    await view.submit();
    openProof(route, 'second-proof');
    await flushPromises();
    finish?.(status === 204 ? new Response(null, { status }) : Response.json({}, { status }));
    await flushPromises();

    expect(view.wrapper.text()).not.toContain(success);
    expect(view.wrapper.text()).not.toContain('invalid or expired');
    expect(view.control().exists()).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(1);
    await view.submit();
    await flushPromises();
    expect(JSON.parse(fetch.mock.calls[1]?.[1]?.body as string).token).toBe('second-proof');
    expect(view.wrapper.text()).toContain(success);
  },
);
