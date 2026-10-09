import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import { ApiError } from '../../../src/api/apiError';
import PasswordSecurityForm from '../../../src/features/configuration/account/components/PasswordSecurityForm.vue';

const state = vi.hoisted(() => ({
  changePassword: vi.fn(),
  clear: vi.fn(),
  isAuthenticated: { value: true },
  replace: vi.fn(),
}));
vi.mock('../../../src/features/configuration/account/api/changePassword', () => ({
  changePassword: state.changePassword,
}));
vi.mock('../../../src/features/session/composables/useSession', () => ({
  useSession: () => ({ clear: state.clear, isAuthenticated: state.isAuthenticated }),
}));
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRouter: () => ({ replace: state.replace }),
}));

afterEach(() => vi.clearAllMocks());

describe('password security form', () => {
  it('sends only current and new passwords, clears session, and returns to login on success', async () => {
    state.changePassword.mockResolvedValue(undefined);
    const wrapper = mount(PasswordSecurityForm, { global: { plugins: [PrimeVue] } });
    await wrapper.get('#current-password').setValue('current secret');
    await wrapper.get('#new-password').setValue('a new password without an invented strength rule');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(state.changePassword).toHaveBeenCalledWith({
      current_password: 'current secret',
      new_password: 'a new password without an invented strength rule',
    });
    expect(state.clear).toHaveBeenCalledOnce();
    expect(state.replace).toHaveBeenCalledWith({ name: 'login' });
    expect((wrapper.get('#current-password').element as HTMLInputElement).value).toBe('');
    expect((wrapper.get('#new-password').element as HTMLInputElement).value).toBe('');
  });

  it('keeps failure guidance safe and clears both fields on cancel', async () => {
    state.changePassword.mockRejectedValue(
      new ApiError(401, 'authentication_required', 'secret detail'),
    );
    const wrapper = mount(PasswordSecurityForm, { global: { plugins: [PrimeVue] } });
    await wrapper.get('#current-password').setValue('wrong');
    await wrapper.get('#new-password').setValue('new');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('Sign in again and check your current password.');
    expect(wrapper.text()).not.toContain('secret detail');
    await wrapper.get('button[type="button"]').trigger('click');
    expect((wrapper.get('#current-password').element as HTMLInputElement).value).toBe('');
    expect((wrapper.get('#new-password').element as HTMLInputElement).value).toBe('');
    expect(state.clear).not.toHaveBeenCalled();
  });
});
