import { flushPromises, mount } from '@vue/test-utils';
import { reactive, ref } from 'vue';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import PrimeVue from 'primevue/config';
import { beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/apiError';
import IndustryRows from '@/features/configuration/ideal-client-profiles/components/IndustryRows.vue';
import CompanySizeRows from '@/features/configuration/ideal-client-profiles/components/CompanySizeRows.vue';
import GeographyRows from '@/features/configuration/ideal-client-profiles/components/GeographyRows.vue';
import ExclusionRows from '@/features/configuration/ideal-client-profiles/components/ExclusionRows.vue';
import ProfilePage from '@/features/profile/pages/ProfilePage.vue';

const state = vi.hoisted(() => ({
  request: vi.fn(),
  session: { value: null as unknown },
  security: { value: { recovery_email: 'delivery@example.com', email_verified: true } },
}));
vi.mock('@/features/account-lifecycle/composables/useAccountSecurity', () => ({
  useAccountSecurity: () => ({ data: state.security }),
}));
vi.mock('@/api/client', () => ({ apiRequest: state.request, configureApiClient: vi.fn() }));
vi.mock('@/features/session/composables/useSession', () => ({
  useSession: () => ({ context: state.session }),
}));
vi.mock(
  '@/features/configuration/ideal-client-profiles/composables/useConfigurationOptions',
  () => ({
    useConfigurationOptions: () => ({
      data: { value: { industries: [], countries: [], company_sizes: [] } },
      isPending: { value: false },
      isError: { value: false },
    }),
  }),
);
const icp = {
  id: 'icp-1',
  business_id: 'business-1',
  name: 'Engineering teams',
  industries: [],
  company_sizes: [],
  geographies: [],
  exclusions: [],
  created_at: '2026-11-01',
  updated_at: '2026-11-01',
};
const saved = {
  business: { id: 'business-1', owner_user_id: 'user-1', name: 'Fluke Design' },
  user: { id: 'user-1', first_name: 'Craig', last_name: 'Phillips', email: 'craig@example.com' },
  service_offering: {
    id: 'offering-1',
    name: 'Design',
    description: 'Product design for startups.',
  },
  ideal_client_profile: icp,
};
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = mount(ProfilePage, {
    global: {
      plugins: [PrimeVue, [VueQueryPlugin, { queryClient: client }]],
      stubs: { Dialog: { props: ['visible'], template: '<div v-if="visible"><slot /></div>' } },
    },
  });
  return { wrapper, client };
}
beforeEach(() => {
  vi.resetAllMocks();
  state.session = ref({ account_id: 'account-1', user_id: 'user-1', csrf_token: 'csrf' });
  state.request.mockImplementation(async (path, options) => {
    if (path === '/api/v1/me/business/setup')
      return options?.method === 'PUT'
        ? {
            ...saved,
            business: { ...saved.business, name: options.body.business_name },
            user: {
              ...saved.user,
              email: options.body.email,
              first_name: options.body.your_name.split(' ')[0],
              last_name: options.body.your_name.split(' ').slice(1).join(' '),
            },
            ideal_client_profile: {
              ...saved.ideal_client_profile,
              ...options.body.ideal_client_profile,
            },
            service_offering: {
              ...saved.service_offering,
              description: options.body.service_description,
            },
          }
        : structuredClone(saved);
    throw new Error('Unexpected API request: ' + path);
  });
});
it('shows the approved minimal fields without services, strategy or professional profile controls', async () => {
  const { wrapper } = setup();
  await flushPromises();
  expect(wrapper.find('#business-name').exists()).toBe(true);
  expect(wrapper.get('#your-name').element).toHaveProperty('value', 'Craig Phillips');
  expect(wrapper.get('#profile-email').element).toHaveProperty('value', 'craig@example.com');
  expect(wrapper.get('#service-description').element).toHaveProperty(
    'value',
    'Product design for startups.',
  );
  expect(wrapper.text()).not.toMatch(
    /Professional summary|Leadership|Add a service|Save discovery setup/,
  );
});
it('keeps ICP edits local and saves the entire profile in one request', async () => {
  const { wrapper, client } = setup();
  await flushPromises();
  await wrapper.get('button[aria-label="Edit ICP"]').trigger('click');
  await wrapper.get('#icp-name').setValue('Seed-stage engineering teams');
  await wrapper.get('form.icp-form').trigger('submit');
  expect(state.request.mock.calls.filter(([, options]) => options?.method)).toHaveLength(0);
  await wrapper.get('#service-description').setValue('Research and product design.');
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  await wrapper.get('form.profile-form').trigger('submit');
  await flushPromises();
  expect(state.request).toHaveBeenCalledWith('/api/v1/me/business/setup', {
    method: 'PUT',
    body: {
      business_name: 'Fluke Design',
      your_name: 'Craig Phillips',
      email: 'craig@example.com',
      service_description: 'Research and product design.',
      ideal_client_profile: {
        name: 'Seed-stage engineering teams',
        industries: [],
        company_sizes: [],
        geographies: [],
        exclusions: [],
      },
    },
  });
  expect(state.request.mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(
    1,
  );
  expect(wrapper.text()).toContain('Seed-stage engineering teams');
  expect(wrapper.text()).toContain('Profile saved');
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['prospecting', 'account-1:user-1:csrf'] });
});
it('shows a pending button and confirms the profile update beside it after the save settles', async () => {
  const { wrapper } = setup();
  await flushPromises();
  let finish!: (response: typeof saved) => void;
  state.request.mockImplementationOnce(
    () => new Promise<typeof saved>((resolve) => (finish = resolve)),
  );
  await wrapper.get('#business-name').setValue('Updated studio');
  await wrapper.get('form.profile-form').trigger('submit');
  await flushPromises();
  const footer = wrapper.get('.profile-footer');
  expect(footer.get('button[type="submit"]').text()).toBe('Saving…');
  expect(footer.get('button[type="submit"]').attributes('disabled')).toBeDefined();
  expect(footer.text()).not.toContain('Profile saved');

  finish({ ...saved, business: { ...saved.business, name: 'Updated studio' } });
  await flushPromises();
  expect(footer.get('[role="status"]').text()).toBe('Profile saved.');
  expect(footer.get('button[type="submit"]').text()).toBe('Save profile');

  await wrapper.get('#business-name').setValue('Another draft');
  expect(footer.text()).not.toContain('Profile saved');
});

it('discards cancelled ICP dialog edits while retaining the profile draft', async () => {
  const { wrapper } = setup();
  await flushPromises();
  await wrapper.get('#business-name').setValue('My updated business');
  await wrapper.get('button[aria-label="Edit ICP"]').trigger('click');
  await wrapper.get('#icp-name').setValue('Discard me');
  await wrapper.get('button[aria-label="Cancel ICP changes"]').trigger('click');
  expect(wrapper.text()).toContain('Engineering teams');
  expect(wrapper.text()).not.toContain('Discard me');
  expect(wrapper.get('#business-name').element).toHaveProperty('value', 'My updated business');
});
it('retains the draft after a failed save and does not claim it was saved', async () => {
  const { wrapper } = setup();
  await flushPromises();
  state.request.mockRejectedValueOnce(new TypeError('network unavailable'));
  await wrapper.get('#service-description').setValue('Keep my service draft.');
  await wrapper.get('form.profile-form').trigger('submit');
  await flushPromises();
  expect(wrapper.get('#service-description').element).toHaveProperty(
    'value',
    'Keep my service draft.',
  );
  expect(wrapper.text()).toContain('could not be confirmed');
  expect(wrapper.text()).not.toContain('Profile saved');
});

it('shows the verified delivery address separately from the editable contact email', async () => {
  const { wrapper } = setup();
  await flushPromises();
  expect(wrapper.get('#profile-email').element).toHaveProperty('value', 'craig@example.com');
  expect(wrapper.text()).toContain('Verified delivery email: delivery@example.com');
  expect(wrapper.text()).toContain(
    'Changing your contact email does not change your verified delivery address.',
  );
});

it('opens the ICP draft with nested server validation errors and retains other edits', async () => {
  const { wrapper } = setup();
  await flushPromises();
  await wrapper.get('#business-name').setValue('Retain my business change');
  state.request.mockRejectedValueOnce(
    new ApiError(422, 'validation_error', 'Review the highlighted fields.', [
      { path: ['ideal_client_profile', 'name'], message: 'Choose a valid ICP name.' },
    ]),
  );
  await wrapper.get('form.profile-form').trigger('submit');
  await flushPromises();
  expect(wrapper.find('#icp-name').exists()).toBe(true);
  expect(wrapper.get('#icp-name').attributes('aria-invalid')).toBe('true');
  expect(wrapper.text()).toContain('Choose a valid ICP name.');
  expect(wrapper.get('#business-name').element).toHaveProperty(
    'value',
    'Retain my business change',
  );
});

it.each([
  { section: 'industries', component: IndustryRows, row: { name: 'Software' } },
  { section: 'company_sizes', component: CompanySizeRows, row: { band: '11-100' } },
  { section: 'geographies', component: GeographyRows, row: { kind: 'country', value: 'GB' } },
  {
    section: 'exclusions',
    component: ExclusionRows,
    row: { kind: 'geography', geography: { kind: 'country', value: 'DE' } },
  },
])(
  'applies, saves and reopens reactive $section selections without losing their values',
  async ({ section, component, row }) => {
    const { wrapper } = setup();
    await flushPromises();
    await wrapper.get('button[aria-label="Edit ICP"]').trigger('click');
    wrapper.getComponent(component).vm.$emit('update:modelValue', [reactive(row)]);
    await wrapper.get('form.icp-form').trigger('submit');
    await flushPromises();
    expect(wrapper.find('form.icp-form').exists()).toBe(false);
    await wrapper.get('form.profile-form').trigger('submit');
    await flushPromises();
    const puts = state.request.mock.calls.filter(([, options]) => options?.method === 'PUT');
    expect(puts).toHaveLength(1);
    expect(puts[0]?.[1].body.ideal_client_profile[section]).toEqual([row]);
    expect(wrapper.text()).toContain('Profile saved');
    await wrapper.get('button[aria-label="Edit ICP"]').trigger('click');
    expect(wrapper.getComponent(component).props('modelValue')).toEqual([row]);
  },
);

it('warns before refreshing when only the unapplied ICP dialog has changes', async () => {
  const { wrapper } = setup();
  await flushPromises();
  await wrapper.get('button[aria-label="Edit ICP"]').trigger('click');
  await wrapper.get('#icp-name').setValue('Not applied yet');
  const refresh = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(refresh);
  expect(refresh.defaultPrevented).toBe(true);
  await wrapper.get('button[aria-label="Cancel ICP changes"]').trigger('click');
  const cleanRefresh = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(cleanRefresh);
  expect(cleanRefresh.defaultPrevented).toBe(false);
});

it('retains the editable draft after a background refresh fails and offers retry', async () => {
  const { wrapper, client } = setup();
  await flushPromises();
  await wrapper.get('#business-name').setValue('My retained draft');
  state.request.mockRejectedValueOnce(new Error('temporary GET failure'));
  await client.refetchQueries({ queryKey: ['business-setup', 'account-1:user-1:csrf'] });
  await flushPromises();
  expect(wrapper.find('#business-name').exists()).toBe(true);
  expect(wrapper.get('#business-name').element).toHaveProperty('value', 'My retained draft');
  expect(wrapper.find('button[aria-label="Retry profile"]').exists()).toBe(true);
});

it('keeps the confirmed PUT result when an older profile GET finishes later', async () => {
  const { wrapper, client } = setup();
  await flushPromises();
  let finishGet!: (value: unknown) => void;
  state.request.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishGet = resolve;
      }),
  );
  const refresh = client.refetchQueries({ queryKey: ['business-setup', 'account-1:user-1:csrf'] });
  await flushPromises();
  await wrapper.get('#business-name').setValue('Confirmed new business name');
  await wrapper.get('form.profile-form').trigger('submit');
  await flushPromises();
  finishGet(structuredClone(saved));
  await refresh;
  await flushPromises();
  expect(wrapper.get('#business-name').element).toHaveProperty(
    'value',
    'Confirmed new business name',
  );
  expect(client.getQueryData(['business-setup', 'account-1:user-1:csrf'])).toMatchObject({
    business: { name: 'Confirmed new business name' },
  });
});

it.each([
  ['business_name', '#business-name'],
  ['your_name', '#your-name'],
  ['email', '#profile-email'],
  ['service_description', '#service-description'],
])('associates the %s validation error with its field', async (field, selector) => {
  const { wrapper } = setup();
  await flushPromises();
  await wrapper.get('#business-name').setValue('Changed business');
  state.request.mockRejectedValueOnce(
    new ApiError(422, 'validation_error', 'Review the highlighted fields.', [
      { path: [field], message: 'Please correct this value.' },
    ]),
  );
  await wrapper.get('form.profile-form').trigger('submit');
  await flushPromises();
  const describedBy = wrapper.get(selector).attributes('aria-describedby')?.split(' ') ?? [];
  expect(
    describedBy.some((id) => wrapper.find('#' + id).text() === 'Please correct this value.'),
  ).toBe(true);
});

it('keeps the confirmed contact email when an older account GET finishes later', async () => {
  const { wrapper, client } = setup();
  await flushPromises();
  let finishGet!: (value: unknown) => void;
  const accountKey = ['account', 'account-1', 'user-1'];
  const accountGet = client
    .fetchQuery({
      queryKey: accountKey,
      queryFn: () =>
        new Promise((resolve) => {
          finishGet = resolve;
        }),
    })
    .catch(() => undefined);
  await wrapper.get('#profile-email').setValue('updated@example.com');
  await wrapper.get('form.profile-form').trigger('submit');
  await flushPromises();
  finishGet(structuredClone(saved.user));
  await accountGet;
  await flushPromises();
  expect(client.getQueryData(accountKey)).toMatchObject({ email: 'updated@example.com' });
});

it('does not write the previous identity result after waiting for query cancellation', async () => {
  const { wrapper, client } = setup();
  await flushPromises();
  let finishCancel!: () => void;
  const setData = vi.spyOn(client, 'setQueryData');
  vi.spyOn(client, 'cancelQueries').mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishCancel = resolve;
      }),
  );
  await wrapper.get('#business-name').setValue('Private previous identity edit');
  await wrapper.get('form.profile-form').trigger('submit');
  await flushPromises();
  state.session.value = { account_id: 'account-2', user_id: 'user-2', csrf_token: 'csrf-2' };
  await flushPromises();
  finishCancel();
  await flushPromises();
  expect(setData).not.toHaveBeenCalled();
  expect(wrapper.text()).not.toContain('Private previous identity edit');
});

it('explains an initial configuration conflict without offering a futile retry', async () => {
  state.request.mockRejectedValueOnce(
    new ApiError(409, 'conflict', 'Multiple service offerings exist.'),
  );
  const { wrapper } = setup();
  await flushPromises();
  expect(wrapper.text()).toContain('Multiple service offerings exist.');
  expect(wrapper.text()).toContain('Contact support');
  expect(wrapper.find('button[aria-label="Retry profile"]').exists()).toBe(false);
});
