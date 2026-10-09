import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import { h } from 'vue';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';
import type { components } from '../../../src/api/generated/schema';
import AccountForm from '../../../src/features/configuration/account/components/AccountForm.vue';
import { ApiError } from '../../../src/api/apiError';

const state = vi.hoisted(() => ({
  refetch: vi.fn(),
  save: vi.fn(),
}));
vi.mock('../../../src/features/configuration/account/composables/useAccount', () => ({
  useAccount: () => ({
    account: { refetch: state.refetch },
    save: { mutateAsync: state.save, isPending: { value: false } },
  }),
}));
vi.mock('../../../src/features/account-lifecycle/composables/useAccountSecurity', () => ({
  useAccountSecurity: () => ({
    data: {
      value: {
        username: 'ada',
        email_verification_required: false,
        email_verified: true,
        recovery_email: 'recovery@example.com',
      },
    },
    isPending: { value: false },
    isError: { value: false },
  }),
}));
vi.mock('../../../src/features/session/composables/useSession', () => ({
  useSession: () => ({ clear: vi.fn(), isAuthenticated: { value: true } }),
}));

afterEach(() => vi.clearAllMocks());

type User = components['schemas']['UserResponse'];
const user: User = {
  id: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  first_name: 'Ada',
  last_name: 'Lovelace',
  email: 'ada@example.com',
  phone_number: '+12025550123',
  country_of_residence: 'GB',
  timezone: 'Europe/London',
};

async function renderAccount() {
  const routeComponent = {
    setup: () => () => h(AccountForm, { account: user }),
  };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/account', component: routeComponent }],
  });
  await router.push('/account');
  const wrapper = mount(RouterView, { global: { plugins: [router, PrimeVue] } });
  await flushPromises();
  return wrapper;
}

describe('account form', () => {
  it('keeps an unknown save draft until refresh, blocks replay, then lets Cancel restore refreshed data', async () => {
    state.save.mockRejectedValueOnce(new TypeError('connection lost'));
    state.refetch.mockResolvedValueOnce({ data: { ...user, first_name: 'Grace' }, isError: false });
    const wrapper = await renderAccount();
    await wrapper.get('#account-first-name').setValue('Augusta');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('save outcome is unknown');
    const saveButton = wrapper.findAll('button').find((button) => button.text() === 'Save changes');
    expect(saveButton?.attributes('disabled')).toBeDefined();
    expect((wrapper.get('#account-first-name').element as HTMLInputElement).value).toBe('Augusta');
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Refresh saved data')
      ?.trigger('click');
    await flushPromises();
    expect((wrapper.get('#account-first-name').element as HTMLInputElement).value).toBe('Augusta');
    expect(saveButton?.attributes('disabled')).toBeUndefined();
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Cancel')
      ?.trigger('click');
    expect((wrapper.get('#account-first-name').element as HTMLInputElement).value).toBe('Grace');
  });

  it('maps native account validation to its exact field', async () => {
    state.save.mockRejectedValueOnce(
      new ApiError(422, 'request_failed', 'Check the highlighted fields.', [
        { path: ['email'], message: 'Enter a valid address.' },
      ]),
    );
    const wrapper = await renderAccount();
    await wrapper.get('#account-email').setValue('invalid');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('Enter a valid address.');
  });
});
