import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import PrimeVue from 'primevue/config';
import LoginPage from '../../src/features/session/pages/LoginPage.vue';
import { useSession } from '../../src/features/session/composables/useSession';

afterEach(() => {
  useSession().clear();
  vi.unstubAllGlobals();
});

it('preserves username and explains rejected login without duplicate submission', async () => {
  let calls = 0;
  vi.stubGlobal('fetch', () => {
    calls++;
    return Promise.resolve(
      Response.json(
        { error: { code: 'authentication_required', message: 'Invalid credentials' } },
        { status: 401 },
      ),
    );
  });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/login', component: LoginPage }],
  });
  await router.push('/login');
  const wrapper = mount(LoginPage, { global: { plugins: [router, PrimeVue] } });
  await wrapper.get('#login-username').setValue('ada');
  await wrapper.get('#login-password').setValue('wrong-password');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('Invalid credentials');
  expect((wrapper.get('#login-username').element as HTMLInputElement).value).toBe('ada');
  expect((wrapper.get('#login-password').element as HTMLInputElement).value).toBe('');
  expect(calls).toBe(1);
});
