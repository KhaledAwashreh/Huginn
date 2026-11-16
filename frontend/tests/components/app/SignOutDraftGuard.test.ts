/* eslint-disable vue/one-component-per-file */
import { flushPromises, mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { afterEach, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';
import AppShell from '@/app/components/AppShell.vue';
import UserMenu from '@/app/components/UserMenu.vue';
import ServiceOfferingForm from '@/features/configuration/offerings/components/ServiceOfferingForm.vue';
import type { components } from '@/api/generated/schema';

const mocks = vi.hoisted(() => ({ logout: vi.fn() }));

vi.mock('@/features/session/composables/useSession', () => ({
  useSession: () => ({
    context: { value: { account_id: 'account', user_id: 'user' } },
    isAdministrator: { value: false },
    isAuthenticated: { value: true },
    logout: mocks.logout,
  }),
}));

vi.mock('@/features/configuration/account/composables/useAccount', () => ({
  useAccount: () => ({
    account: {
      data: { value: { first_name: 'Ada', last_name: 'Browser', email: 'ada@example.test' } },
    },
  }),
}));

const menuStub = defineComponent({
  props: { model: { type: Array, required: true } },
  setup(props) {
    return () =>
      h(
        'div',
        (props.model as Array<{ label?: string; command?: () => void }>).map((item) =>
          item.label
            ? h(
                'button',
                { type: 'button', 'data-menu-label': item.label, onClick: item.command },
                item.label,
              )
            : null,
        ),
      );
  },
});

const navigationStub = defineComponent({
  components: { UserMenu },
  emits: ['openSettings'],
  template: '<UserMenu @open="$emit(\'openSettings\', $event)" />',
});

const response: components['schemas']['ServiceOfferingResponse'] = {
  id: 'service-id',
  business_id: 'business-id',
  name: 'Advisory',
  description: 'Launch support',
  created_at: '2026-10-08T00:00:00Z',
  updated_at: '2026-10-08T00:00:00Z',
};

async function mountWorkspace(save = vi.fn().mockResolvedValue(response)) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/offerings/new',
        name: 'offering-create',
        component: ServiceOfferingForm,
        props: {
          initial: { name: '', description: '' },
          existing: false,
          save,
          refreshSaved: vi.fn().mockResolvedValue(null),
          afterSave: vi.fn(),
        },
        meta: { requiresAuth: true },
      },
      {
        path: '/recommendations',
        component: { template: '<div>Recommendations</div>' },
        meta: { requiresAuth: true },
      },
      { path: '/login', component: { template: '<div>Login</div>' } },
    ],
  });
  await router.push('/offerings/new');
  const harness = defineComponent({
    setup() {
      return () => h(AppShell, null, { default: () => h(RouterView) });
    },
  });
  const wrapper = mount(harness, {
    global: {
      plugins: [PrimeVue, router],
      stubs: { AppNavigation: navigationStub, Menu: menuStub, SettingsDialog: true },
    },
  });
  return { router, wrapper };
}

async function clickSignOut(wrapper: ReturnType<typeof mount>): Promise<void> {
  await wrapper.get('[data-menu-label="Sign out"]').trigger('click');
  await flushPromises();
}

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

it('keeps a declined offering draft and does not send logout', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const { router, wrapper } = await mountWorkspace();
  await wrapper.get('#offering-name').setValue('Draft service');
  await wrapper.get('#offering-description').setValue('Draft description');

  await clickSignOut(wrapper);

  expect(confirm).toHaveBeenCalledOnce();
  expect(router.currentRoute.value.path).toBe('/offerings/new');
  expect((wrapper.get('#offering-name').element as HTMLInputElement).value).toBe('Draft service');
  expect(mocks.logout).not.toHaveBeenCalled();
  wrapper.unmount();
});

it('runs the actual offering route guard before logout and allows logout on the landing route', async () => {
  const order: string[] = [];
  const confirm = vi.spyOn(window, 'confirm').mockImplementation(() => {
    order.push('guard');
    return true;
  });
  mocks.logout.mockImplementation(async () => {
    order.push('logout');
  });
  const { router, wrapper } = await mountWorkspace();
  await wrapper.get('#offering-name').setValue('Draft service');
  await wrapper.get('#offering-description').setValue('Draft description');

  await clickSignOut(wrapper);

  expect(confirm).toHaveBeenCalledOnce();
  expect(order).toEqual(['guard', 'logout']);
  expect(router.currentRoute.value.path).toBe('/login');
  expect(mocks.logout).toHaveBeenCalledOnce();
  wrapper.unmount();
});

it('does not logout while an offering save is pending', async () => {
  const confirm = vi.spyOn(window, 'confirm');
  const save = vi.fn(() => new Promise<typeof response>(() => {}));
  const { router, wrapper } = await mountWorkspace(save);
  await wrapper.get('#offering-name').setValue('Draft service');
  await wrapper.get('#offering-description').setValue('Draft description');
  await wrapper.get('form').trigger('submit');
  await flushPromises();

  await clickSignOut(wrapper);

  expect(save).toHaveBeenCalledOnce();
  expect(confirm).not.toHaveBeenCalled();
  expect(router.currentRoute.value.path).toBe('/offerings/new');
  expect(mocks.logout).not.toHaveBeenCalled();
  wrapper.unmount();
});

it('does not logout if a route guard errors during the preflight', async () => {
  const { router, wrapper } = await mountWorkspace();
  const routeError = vi.fn();
  router.onError(routeError);
  router.beforeEach((to) => {
    if (to.path === '/recommendations') throw new Error('preflight failed');
  });

  await clickSignOut(wrapper);

  expect(routeError).toHaveBeenCalledOnce();
  expect(router.currentRoute.value.path).toBe('/offerings/new');
  expect(mocks.logout).not.toHaveBeenCalled();
  expect(wrapper.get('[role="alert"]').text()).toContain('Your draft is still here');
  wrapper.unmount();
});

it('keeps logout errors visible and ignores duplicate requests while logout is pending', async () => {
  let rejectLogout!: (error: Error) => void;
  mocks.logout.mockReturnValue(
    new Promise<void>((_resolve, reject) => {
      rejectLogout = reject;
    }),
  );
  const { router, wrapper } = await mountWorkspace();

  await clickSignOut(wrapper);
  expect(router.currentRoute.value.path).toBe('/recommendations');
  await clickSignOut(wrapper);
  expect(mocks.logout).toHaveBeenCalledOnce();

  rejectLogout(new Error('offline'));
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toBe('Sign out failed. Try again.');
  expect(router.currentRoute.value.path).toBe('/recommendations');
  wrapper.unmount();
});

it('can sign out when already on the authenticated landing route', async () => {
  mocks.logout.mockResolvedValue(undefined);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/recommendations',
        component: { template: '<div>Recommendations</div>' },
        meta: { requiresAuth: true },
      },
      { path: '/login', component: { template: '<div>Login</div>' } },
    ],
  });
  await router.push('/recommendations');
  const wrapper = mount(UserMenu, {
    global: { plugins: [PrimeVue, router], stubs: { Menu: menuStub } },
  });

  await clickSignOut(wrapper);

  expect(mocks.logout).toHaveBeenCalledOnce();
  expect(router.currentRoute.value.path).toBe('/login');
  wrapper.unmount();
});
