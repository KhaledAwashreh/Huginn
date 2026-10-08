import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import PrimeVue from 'primevue/config';
import CreateAccountPage from '../../src/features/account-lifecycle/pages/CreateAccountPage.vue';
import VerifyEmailPage from '../../src/features/account-lifecycle/pages/VerifyEmailPage.vue';
import ResetPasswordPage from '../../src/features/account-lifecycle/pages/ResetPasswordPage.vue';
import ForgotPasswordPage from '../../src/features/account-lifecycle/pages/ForgotPasswordPage.vue';
import CheckEmailPage from '../../src/features/account-lifecycle/pages/CheckEmailPage.vue';
import RecoveryEmailEnrollment from '../../src/features/account-lifecycle/components/RecoveryEmailEnrollment.vue';
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query';
import { useSession } from '../../src/features/session/composables/useSession';
import { configureApiClient } from '../../src/api/client';
import type { Component } from 'vue';
import {
  COUNTRY_CALLING_CODES,
  COUNTRY_OPTIONS,
} from '../../src/features/account-lifecycle/forms/signupDraft';
import { validateLifecyclePassword } from '../../src/features/account-lifecycle/forms/resetPasswordDraft';

const mounted: { unmount: () => void }[] = [];
const clients: QueryClient[] = [];

async function render(component: Component, path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path, component },
      { path: '/check-email', name: 'check-email', component: CheckEmailPage },
      { path: '/login', component: { template: '<h1>Sign in</h1>' } },
      { path: '/forgot-password', component: { template: '<h1>Forgot password</h1>' } },
    ],
  });
  await router.push(path);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(queryClient);
  const wrapper = mount(component, {
    attachTo: document.body,
    global: {
      plugins: [router, PrimeVue, [VueQueryPlugin, { queryClient }]],
    },
  });
  mounted.push(wrapper);
  return wrapper;
}
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  for (const client of clients.splice(0)) client.clear();
  useSession().clear();
  configureApiClient({});
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.history.replaceState({}, '', '/');
});

it('requires signup identity fields, serializes its contract, guards pending and clears secrets on failure', async () => {
  let finish: ((value: Response) => void) | undefined;
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(
    () =>
      new Promise<Response>((resolve) => {
        finish = resolve;
      }),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(CreateAccountPage, '/create-account');
  const fields = {
    username: 'ada',
    password: 'SignUp!12345',
    first_name: 'Ada',
    last_name: 'Lovelace',
    email: 'ada@example.test',
    country_of_residence: 'GB',
    phone_number: '1234 567-890',
    timezone: 'Europe/London',
  };
  for (const [name, value] of Object.entries(fields)) {
    const input = wrapper.get(`#signup-${name}`);
    if (name !== 'timezone') expect(input.attributes('required')).toBeDefined();
    await input.setValue(value);
  }
  expect(wrapper.text()).toContain('Verify your email before signing in');
  expect(wrapper.get('#signup-password').attributes('autocomplete')).toBe('new-password');
  await wrapper.get('form').trigger('submit');
  await wrapper.get('form').trigger('submit');
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetch.mock.calls[0]?.[1]?.body as string)).toEqual({
    ...fields,
    phone_number: '+441234567890',
  });
  finish?.(
    Response.json(
      { detail: [{ loc: ['body', 'phone_number'], msg: 'Invalid phone number' }] },
      { status: 422 },
    ),
  );
  await flushPromises();
  expect(wrapper.text()).toContain('Invalid phone number');
  expect((wrapper.get('#signup-email').element as HTMLInputElement).value).toBe('ada@example.test');
  expect((wrapper.get('#signup-password').element as HTMLInputElement).value).toBe('');
});

it('offers every calling region in name order and keeps the national number when the country changes', async () => {
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(Response.json({ message: 'Check your email for next steps' }, { status: 202 })),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(CreateAccountPage, '/create-account');
  const countrySelect = wrapper.get('#signup-country_of_residence');
  const options = countrySelect.findAll('option').filter((option) => option.element.value);
  expect(options).toHaveLength(Object.keys(COUNTRY_CALLING_CODES).length);
  expect(options.map((option) => option.element.value)).toEqual(
    COUNTRY_OPTIONS.map((country) => country.code),
  );
  expect(options.map((option) => option.text()).sort((a, b) => a.localeCompare(b, 'en'))).toEqual(
    options.map((option) => option.text()),
  );
  const formControlOrder = wrapper
    .get('form')
    .findAll('select, input')
    .map((control) => control.attributes('id'));
  expect(formControlOrder.indexOf('signup-country_of_residence')).toBeLessThan(
    formControlOrder.indexOf('signup-phone_number'),
  );

  await countrySelect.setValue('GB');
  await wrapper.get('#signup-phone_number').setValue('1234 567-890');
  expect((wrapper.get('#signup-phone-prefix').element as HTMLInputElement).value).toBe('+44');
  await countrySelect.setValue('US');
  expect((wrapper.get('#signup-phone-prefix').element as HTMLInputElement).value).toBe('+1');
  expect((wrapper.get('#signup-phone_number').element as HTMLInputElement).value).toBe(
    '1234 567-890',
  );

  await wrapper.get('#signup-password').setValue('SignUp!12345');
  await wrapper.get('#signup-username').setValue('ada');
  await wrapper.get('#signup-first_name').setValue('Ada');
  await wrapper.get('#signup-last_name').setValue('Lovelace');
  await wrapper.get('#signup-email').setValue('ada@example.test');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(JSON.parse(fetch.mock.calls[0]?.[1]?.body as string)).toMatchObject({
    country_of_residence: 'US',
    phone_number: '+11234567890',
  });
});

it('rejects invalid phone input locally and focuses its field without posting', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(CreateAccountPage, '/create-account');
  await wrapper.get('#signup-password').setValue('SignUp!12345');
  await wrapper.get('#signup-username').setValue('ada');
  await wrapper.get('#signup-first_name').setValue('Ada');
  await wrapper.get('#signup-last_name').setValue('Lovelace');
  await wrapper.get('#signup-email').setValue('ada@example.test');
  await wrapper.get('#signup-country_of_residence').setValue('GB');
  await wrapper.get('#signup-phone_number').setValue('letters');
  await wrapper.get('form').trigger('submit');
  await flushPromises();

  expect(fetch).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain('Enter a valid national phone number');
  expect(document.activeElement).toBe(wrapper.get('#signup-phone_number').element);
  expect((wrapper.get('#signup-password').element as HTMLInputElement).value).toBe('');
});

it('requires a country selection before submitting signup', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(CreateAccountPage, '/create-account');
  await wrapper.get('#signup-password').setValue('SignUp!12345');
  await wrapper.get('#signup-username').setValue('ada');
  await wrapper.get('#signup-first_name').setValue('Ada');
  await wrapper.get('#signup-last_name').setValue('Lovelace');
  await wrapper.get('#signup-email').setValue('ada@example.test');
  await wrapper.get('#signup-phone_number').setValue('1234567890');
  await wrapper.get('form').trigger('submit');

  expect(fetch).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain('Country of residence is required');
  expect(document.activeElement).toBe(wrapper.get('#signup-country_of_residence').element);
});

it.each(['   ', 'not-an-email'])(
  'rejects invalid signup email %j without posting',
  async (email) => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const wrapper = await render(CreateAccountPage, '/create-account');
    for (const [name, value] of Object.entries({
      username: 'ada',
      password: 'SignUp!12345',
      first_name: 'Ada',
      last_name: 'Lovelace',
      email,
      country_of_residence: 'GB',
      phone_number: '1234567890',
    }))
      await wrapper.get(`#signup-${name}`).setValue(value);
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(fetch).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain(email.trim() ? 'valid email address' : 'Email is required');
    expect(document.activeElement).toBe(wrapper.get('#signup-email').element);
  },
);

it.each([
  ['too short', 'Ab!1234'],
  ['too long', 'Ab!12345678901234'],
  ['missing a letter', '!1234567'],
  ['missing an ASCII digit', 'Abcdefg!'],
  ['missing punctuation or symbol', 'Abcdefg1'],
  ['contains a control character', 'Abcde\u0007f1!'],
])('requires the signup password rule for input that is %s', (_reason, password) => {
  expect(validateLifecyclePassword(password)).not.toBeNull();
});

it('accepts a Unicode letter with an ASCII digit and Unicode punctuation or symbol', () => {
  expect(validateLifecyclePassword('éééééé1!')).toBeNull();
  expect(validateLifecyclePassword('Abcdefg١!')).not.toBeNull();
});

it('rejects reset passwords locally, preserves the proof, and clears the attempted secret', async () => {
  window.history.replaceState({}, '', '/reset-password#token=reset-proof');
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(ResetPasswordPage, '/reset-password');
  await wrapper.get('#reset-password').setValue('Abcdefg1');
  await wrapper.get('form').trigger('submit');

  expect(fetch).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain('punctuation or symbol');
  expect(wrapper.find('form').exists()).toBe(true);
  expect((wrapper.get('#reset-password').element as HTMLInputElement).value).toBe('');
  expect(document.activeElement).toBe(wrapper.get('#reset-password').element);
});

it('removes proof from history and consumes only on explicit verification', async () => {
  window.history.replaceState({}, '', '/verify-email#token=secret-proof');
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(new Response(null, { status: 204 })),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(VerifyEmailPage, '/verify-email');
  expect(window.location.hash).toBe('');
  expect(fetch).not.toHaveBeenCalled();
  await wrapper.get('button').trigger('click');
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetch.mock.calls[0]?.[1]?.body as string)).toEqual({ token: 'secret-proof' });
  expect(wrapper.text()).toContain('Email verified');
  expect(wrapper.get('a').attributes('href')).toBe('/login');
});

it('expired proof offers email resend and rate limits require a wait without retries', async () => {
  window.history.replaceState({}, '', '/verify-email#token=expired-proof');
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(Response.json({}, { status: 422 })),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(VerifyEmailPage, '/verify-email');
  await wrapper.get('button').trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('invalid or expired');
  expect(wrapper.find('button[type="button"]').exists()).toBe(false);
  fetch.mockImplementation(() => Promise.resolve(Response.json({}, { status: 429 })));
  await wrapper.get('#resend-email').setValue('ada@example.test');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('Wait');
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('reset explicitly submits proof and new password then links to login', async () => {
  window.history.replaceState({}, '', '/reset-password#token=reset-proof');
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(new Response(null, { status: 204 })),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(ResetPasswordPage, '/reset-password');
  expect(fetch).not.toHaveBeenCalled();
  await wrapper.get('#reset-password').setValue('ResetNow!12345');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(JSON.parse(fetch.mock.calls[0]?.[1]?.body as string)).toEqual({
    token: 'reset-proof',
    new_password: 'ResetNow!12345',
  });
  expect(wrapper.text()).toContain('Password saved');
  expect(wrapper.get('a').attributes('href')).toBe('/login');
});

it('forgot password asks for email and passes it through to the generic receipt page', async () => {
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(Response.json({ message: 'Check your email for next steps' }, { status: 202 })),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(ForgotPasswordPage, '/forgot-password');
  expect(wrapper.text()).toContain('Email');
  await wrapper.get('#forgot-email').setValue('ada@example.test');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(JSON.parse(fetch.mock.calls[0]?.[1]?.body as string)).toEqual({
    email: 'ada@example.test',
  });
  expect(fetch.mock.calls[0]?.[0]).toBe('/api/v1/password-resets');
  expect(wrapper.vm.$router.currentRoute.value.fullPath).toBe('/check-email');
  expect(wrapper.vm.$router.options.history.state.email).toBe('ada@example.test');
  expect(wrapper.vm.$router.options.history.state.purpose).toBe('reset');
});

it.each(['   ', 'not-an-email'])(
  'rejects invalid recovery email %j without posting',
  async (email) => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const wrapper = await render(ForgotPasswordPage, '/forgot-password');
    await wrapper.get('#forgot-email').setValue(email);
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(fetch).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain(
      email.trim() ? 'valid email address' : 'Enter your email address',
    );
    expect(document.activeElement).toBe(wrapper.get('#forgot-email').element);
  },
);

it('check-email uses its email and purpose state for resend and keeps the email draft after errors', async () => {
  window.history.replaceState({ email: 'ada@example.test', purpose: 'reset' }, '', '/check-email');
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(Response.json({}, { status: 429 })),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(CheckEmailPage, '/check-email');
  expect((wrapper.get('#receipt-email').element as HTMLInputElement).value).toBe(
    'ada@example.test',
  );
  await wrapper.get('form').trigger('submit');
  await flushPromises();

  expect(JSON.parse(fetch.mock.calls[0]?.[1]?.body as string)).toEqual({
    email: 'ada@example.test',
  });
  expect(wrapper.text()).toContain('Wait');
  expect((wrapper.get('#receipt-email').element as HTMLInputElement).value).toBe(
    'ada@example.test',
  );
  expect(wrapper.find('[role="status"]').exists()).toBe(false);
});

it('initial enrollment has no replacement address control and sends empty JSON with session CSRF', async () => {
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>((url) =>
    Promise.resolve(
      url.endsWith('/sessions/current')
        ? Response.json({
            account_id: '1',
            user_id: '2',
            csrf_token: 'csrf-proof',
            expires_at: '2030-01-01T00:00:00Z',
          })
        : url.endsWith('/account-security')
          ? Response.json({
              username: 'ada',
              email_verification_required: false,
              email_verified: false,
              recovery_email: null,
            })
          : Response.json({ message: 'Check your email for next steps' }, { status: 202 }),
    ),
  );
  vi.stubGlobal('fetch', fetch);
  await useSession().bootstrap();
  const wrapper = await render(RecoveryEmailEnrollment, '/');
  await flushPromises();
  expect(wrapper.text()).toContain('contact email');
  expect(wrapper.find('input').exists()).toBe(false);
  await wrapper.get('button').trigger('click');
  await flushPromises();
  const enrollment = fetch.mock.calls.find(([url]) =>
    url.endsWith('/recovery-email-verifications'),
  );
  expect(enrollment).toBeDefined();
  const options = enrollment?.[1];
  expect(options?.body).toBe('{}');
  expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('csrf-proof');
});

it('missing proofs require reopening a mail link without issuing a request', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  const verify = await render(VerifyEmailPage, '/verify-email');
  expect(verify.text()).toContain('Open the link');
  expect(verify.find('#resend-email').exists()).toBe(true);
  const reset = await render(ResetPasswordPage, '/reset-password');
  expect(reset.text()).toContain('Open the original email link');
  expect(reset.get('a').attributes('href')).toBe('/forgot-password');
  expect(fetch).not.toHaveBeenCalled();
});

it('reset validation preserves proof for an explicit retry and clears attempted password', async () => {
  window.history.replaceState({}, '', '/reset-password#token=reset-proof');
  const fetch = vi.fn(() =>
    Promise.resolve(
      Response.json(
        {
          detail: [{ loc: ['body', 'new_password'], msg: 'The password could not be accepted' }],
        },
        { status: 422 },
      ),
    ),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(ResetPasswordPage, '/reset-password');
  await wrapper.get('#reset-password').setValue('ResetNow!12345');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('The password could not be accepted');
  expect((wrapper.get('#reset-password').element as HTMLInputElement).value).toBe('');
  expect(wrapper.find('form').exists()).toBe(true);
  expect(fetch).toHaveBeenCalledTimes(1);
});

it.each([
  { required: false, verified: true, email: 'verified@example.test' },
  { required: true, verified: false, email: null },
])(
  'does not offer enrollment for verified or verification-required accounts: %o',
  async ({ required, verified, email }) => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(
          url.endsWith('/sessions/current')
            ? Response.json({
                account_id: '3',
                user_id: '4',
                csrf_token: 'csrf-proof',
                expires_at: '2030-01-01T00:00:00Z',
              })
            : Response.json({
                username: 'ada',
                email_verification_required: required,
                email_verified: verified,
                recovery_email: email,
              }),
        ),
      ),
    );
    await useSession().bootstrap();
    const wrapper = await render(RecoveryEmailEnrollment, '/');
    await flushPromises();
    expect(wrapper.find('button').exists()).toBe(false);
    expect(wrapper.find('input').exists()).toBe(false);
    if (verified)
      expect(wrapper.text()).toContain('Verified recovery email: verified@example.test');
  },
);

it('signup omits blank timezone and routes to a generic receipt with email and purpose only', async () => {
  const fetch = vi.fn<(url: string, options?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(Response.json({ message: 'Check your email for next steps' }, { status: 202 })),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(CreateAccountPage, '/create-account');
  const fields = {
    username: 'ada',
    password: 'SignUp!12345',
    first_name: 'Ada',
    last_name: 'Lovelace',
    email: 'ada@example.test',
    country_of_residence: 'GB',
    phone_number: '1234 567-890',
  };
  for (const [name, value] of Object.entries(fields))
    await wrapper.get(`#signup-${name}`).setValue(value);
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(JSON.parse(fetch.mock.calls[0]?.[1]?.body as string)).toEqual({
    ...fields,
    phone_number: '+441234567890',
  });
  expect(wrapper.vm.$router.currentRoute.value.fullPath).toBe('/check-email');
  expect(wrapper.vm.$router.options.history.state.email).toBe('ada@example.test');
  expect(wrapper.vm.$router.options.history.state.password).toBeUndefined();
  expect((wrapper.get('#signup-password').element as HTMLInputElement).value).toBe('');
});

it('submits a valid 16-code-point password containing an emoji verbatim', async () => {
  const password = 'Abcdefghijklm1!😀';
  expect(Array.from(password)).toHaveLength(16);
  const fetch = vi.fn<typeof globalThis.fetch>(() =>
    Promise.resolve(Response.json({ message: 'Check your email for next steps' }, { status: 202 })),
  );
  vi.stubGlobal('fetch', fetch);
  const wrapper = await render(CreateAccountPage, '/create-account');
  for (const [name, value] of Object.entries({
    username: 'ada',
    password,
    first_name: 'Ada',
    last_name: 'Lovelace',
    email: 'ada@example.test',
    country_of_residence: 'US',
    phone_number: '2025550123',
  }))
    await wrapper.get(`#signup-${name}`).setValue(value);
  expect(wrapper.get('#signup-password').attributes('maxlength')).toBeUndefined();
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(JSON.parse(fetch.mock.calls[0]?.[1]?.body as string).password).toBe(password);
});
