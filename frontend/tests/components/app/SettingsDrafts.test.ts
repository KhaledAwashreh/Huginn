import { flushPromises, mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { expect, it, vi } from 'vitest';
import { ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import App from '@/app/App.vue';

vi.mock('@/features/session/composables/useSession', () => ({
  useSession: () => ({
    context: ref({ account_id: 'account', user_id: 'user' }),
    isAdministrator: { value: true },
    isAuthenticated: { value: true },
  }),
}));
vi.mock('@/features/configuration/account/composables/useAccount', () => ({
  useAccount: () => ({ account: { data: { value: undefined }, isPending: { value: true } } }),
}));
vi.mock('@/features/account-lifecycle/composables/useAccountSecurity', () => ({
  useAccountSecurity: () => ({ data: { value: undefined } }),
}));

async function openSecurity() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/matches',
        component: { template: '<div>Matches</div>' },
        meta: { requiresAuth: true },
      },
      { path: '/verify-email', component: { template: '<div>Verify email</div>' } },
    ],
  });
  await router.push('/verify-email');
  await router.push('/matches');
  const wrapper = mount(App, {
    global: {
      plugins: [PrimeVue, router],
      stubs: {
        AppNavigation: {
          template: `<button @click="$emit('open-settings', 'security')">Open security</button>`,
        },
        Dialog: { props: ['visible'], template: '<div v-if="visible"><slot /></div>' },
        RecoveryEmailEnrollment: true,
      },
    },
  });
  await wrapper.get('header button').trigger('click');
  await wrapper.get('#current-password').setValue('draft password');
  return { wrapper, router };
}

it('preserves the password draft when the user declines to switch sections or close Settings', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const { wrapper } = await openSecurity();
  const account = wrapper.findAll('button').find((button) => button.text() === 'Admin');
  expect(wrapper.text()).not.toContain('ICP definition');
  if (!account) throw new Error('Expected an Admin settings button');
  await account.trigger('click');
  await flushPromises();
  expect((wrapper.get('#current-password').element as HTMLInputElement).value).toBe(
    'draft password',
  );

  await wrapper.get('button[aria-label="Close settings"]').trigger('click');
  await flushPromises();
  expect(wrapper.find('#current-password').exists()).toBe(true);
  expect(confirm).toHaveBeenCalledTimes(2);

  confirm.mockReturnValue(true);
  await wrapper.get('button[aria-label="Close settings"]').trigger('click');
  await flushPromises();
  expect(wrapper.find('#current-password').exists()).toBe(false);
});

it('guards browser back when leaving the authenticated shell would discard the draft', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const { wrapper, router } = await openSecurity();

  router.back();
  await flushPromises();
  expect(router.currentRoute.value.path).toBe('/matches');
  expect(wrapper.find('#current-password').exists()).toBe(true);
  expect(confirm).toHaveBeenCalledOnce();

  confirm.mockReturnValue(true);
  router.back();
  await flushPromises();
  expect(router.currentRoute.value.path).toBe('/verify-email');
});
