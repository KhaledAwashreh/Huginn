import { mount } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import UserMenu from '@/app/components/UserMenu.vue';

const account = vi.hoisted(() => ({
  value: { first_name: '', last_name: '', email: 'ada@example.test' },
}));
vi.mock('@/features/configuration/account/composables/useAccount', () => ({
  useAccount: () => ({ account: { data: account } }),
}));
vi.mock('@/features/session/composables/useSession', () => ({
  useSession: () => ({ isAdministrator: { value: false } }),
}));

async function renderMenu() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  });
  await router.push('/');
  return mount(UserMenu, {
    global: {
      plugins: [router],
      stubs: { Menu: { template: '<div><slot name="start" /></div>' } },
    },
  });
}

beforeEach(() => {
  account.value.first_name = '';
  account.value.last_name = '';
});

it('uses the full name and initials with whitespace removed', async () => {
  account.value.first_name = ' Ada ';
  account.value.last_name = ' Lovelace ';
  const menu = await renderMenu();

  expect(menu.get('.visually-hidden').text()).toBe('Ada Lovelace');
  expect(menu.get('.avatar').text()).toBe('AL');
  expect(menu.get('.identity').text()).toBe('Ada Lovelace');
  menu.unmount();
});

it('labels the menu for an account without a display name', async () => {
  const menu = await renderMenu();

  expect(menu.get('.visually-hidden').text()).toBe('Your account');
  expect(menu.find('.avatar svg').exists()).toBe(true);
  menu.unmount();
});
