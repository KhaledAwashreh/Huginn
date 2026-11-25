import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import PrimeVue from 'primevue/config';
import { beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/apiError';
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
  expect(wrapper.text()).toContain('Profile saved');
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['prospecting', 'account-1:user-1:csrf'] });
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
