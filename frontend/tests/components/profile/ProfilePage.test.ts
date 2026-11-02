import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/apiError';
import ProfilePage from '@/features/profile/pages/ProfilePage.vue';

type Query = {
  data: { value: unknown };
  isPending: { value: boolean };
  isError: { value: boolean };
  isFetching: { value: boolean };
  refetch: ReturnType<typeof vi.fn>;
};
const query = (data: unknown): Query => ({
  data: { value: data },
  isPending: { value: false },
  isError: { value: false },
  isFetching: { value: false },
  refetch: vi.fn(),
});
const failed = (): Query => ({ ...query(undefined), isError: { value: true } });
const page = (items: unknown[]) => ({ items, limit: 100, offset: 0, has_more: false });
const service = { id: 'service-1', name: 'Advising', description: 'Monthly advice.' };
const profileData = {
  headline: 'Founder',
  professional_summary: 'A small studio.',
  skills: [],
  updated_at: '2026-10-09T12:00:00Z',
};

const state = vi.hoisted(() => ({
  profile: undefined as unknown,
  offerings: undefined as unknown,
  icps: undefined as unknown,
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
}));

vi.mock('@/features/configuration/account/composables/useAccount', () => ({
  useAccount: () => ({
    account: { data: { value: { first_name: 'Bob', last_name: 'Browser' } } },
  }),
}));
vi.mock('@/features/configuration/professional-profile/composables/useProfessionalProfile', () => ({
  useProfessionalProfile: () => ({ profile: state.profile, save: { mutateAsync: vi.fn() } }),
}));
vi.mock('@/features/configuration/offerings/composables/useServiceOffering', () => ({
  useServiceOffering: () => ({
    list: state.offerings,
    create: { mutateAsync: state.create },
    update: { mutateAsync: state.update },
    remove: { mutateAsync: state.remove },
  }),
}));
vi.mock('@/features/configuration/ideal-client-profiles/composables/useIdealClientProfile', () => ({
  useIdealClientProfile: () => ({ list: state.icps }),
}));

const global = {
  plugins: [PrimeVue],
  stubs: {
    Dialog: { props: ['visible'], template: '<div v-if="visible"><slot /></div>' },
  },
};
const button = (wrapper: VueWrapper, label: string) => {
  const found = wrapper
    .findAll('button')
    .find((item) => item.text() === label || item.attributes('aria-label') === label);
  if (!found) throw new Error(`Expected a button labelled ${label}`);
  return found;
};

beforeEach(() => {
  state.profile = query(profileData);
  state.offerings = query(page([service]));
  state.icps = query(page([]));
  state.create.mockReset();
  state.update.mockReset();
  state.remove.mockReset();
});

describe('profile load failures', () => {
  it('offers a retry when the main profile cannot load', async () => {
    const profile = failed();
    state.profile = profile;
    const wrapper = mount(ProfilePage, { global });
    expect(wrapper.text()).toContain('Your profile could not be loaded.');
    await button(wrapper, 'Retry profile').trigger('click');
    expect(profile.refetch).toHaveBeenCalledOnce();
  });

  it('shows a retry for failed services, never the add-your placeholder', async () => {
    const offerings = failed();
    state.offerings = offerings;
    const wrapper = mount(ProfilePage, { global });
    expect(wrapper.text()).toContain('Your services could not be loaded.');
    expect(wrapper.text()).not.toContain('Add what you sell');
    expect(wrapper.find('button[aria-label="Add a service"]').exists()).toBe(false);
    await button(wrapper, 'Retry services').trigger('click');
    expect(offerings.refetch).toHaveBeenCalledOnce();
  });

  it('shows a retry for a failed ICP list, never the placeholder or add action', async () => {
    const icps = failed();
    state.icps = icps;
    const wrapper = mount(ProfilePage, { global });
    expect(wrapper.text()).toContain('Your ICP definition could not be loaded.');
    expect(wrapper.text()).not.toContain('Describe the clients you want');
    expect(wrapper.find('button[aria-label="Add your ICP"]').exists()).toBe(false);
    await button(wrapper, 'Retry ICP definition').trigger('click');
    expect(icps.refetch).toHaveBeenCalledOnce();
  });

  it('shows the empty placeholders once the lists have loaded empty', () => {
    state.offerings = query(page([]));
    const wrapper = mount(ProfilePage, { global });
    expect(wrapper.text()).toContain('Add what you sell');
    expect(wrapper.text()).toContain('Describe the clients you want');
  });
});

describe('service changes', () => {
  async function openService(wrapper: VueWrapper) {
    await wrapper
      .findAll('button')
      .find((item) => item.text().includes('Advising'))
      ?.trigger('click');
  }

  it('explains a 409 on delete as a strategy using the service', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    state.remove.mockRejectedValue(new ApiError(409, 'referenced', 'Conflict'));
    const wrapper = mount(ProfilePage, { global });
    await openService(wrapper);
    await button(wrapper, 'Remove').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('used by a discovery strategy');
    expect(button(wrapper, 'Save')).toBeTruthy();
  });

  it('reports a network failure as uncertain and requires a refresh before retrying', async () => {
    state.update.mockRejectedValue(new TypeError('Failed to fetch'));
    const offerings = query(page([service]));
    offerings.refetch.mockResolvedValue({ isError: false, data: page([service]) });
    state.offerings = offerings;
    const wrapper = mount(ProfilePage, { global });
    await openService(wrapper);
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('The outcome is uncertain.');
    expect(wrapper.text()).not.toContain('Failed to fetch');
    expect(wrapper.findAll('button').some((item) => item.text() === 'Save')).toBe(false);

    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(state.update).toHaveBeenCalledOnce();

    await button(wrapper, 'Refresh services').trigger('click');
    await flushPromises();
    expect(offerings.refetch).toHaveBeenCalledOnce();
    expect(wrapper.find('form').exists()).toBe(false);
  });
});

describe('features awaiting a backend', () => {
  it('disables them with honest copy and leaves API-backed items working', async () => {
    const wrapper = mount(ProfilePage, { global });
    expect(wrapper.text()).toContain('Your business');
    expect(wrapper.text()).toContain('Business details are coming soon');
    expect(wrapper.text()).toContain('About your business');
    expect(wrapper.text()).toContain('Client list is coming soon.');
    expect(wrapper.text()).toContain('Links are coming soon.');
    expect(wrapper.text()).not.toContain('Links and files');
    expect(wrapper.find('input[type="file"]').exists()).toBe(false);
    const leader = wrapper.findAll('button').find((item) => item.text().includes('Bob Browser'));
    for (const control of [
      button(wrapper, 'Edit business details'),
      button(wrapper, 'Add a leader'),
      button(wrapper, 'Add a client'),
      button(wrapper, 'Add a link'),
      leader,
    ]) {
      expect(control?.attributes('disabled')).toBeDefined();
      expect(control?.attributes('title')).toBe('Coming soon');
    }
    expect(leader?.text()).toContain('Founder');

    for (const label of ['Edit about your business', 'Edit skills', 'Add a service']) {
      expect(button(wrapper, label).attributes('disabled')).toBeUndefined();
    }
    await button(wrapper, 'Add a service').trigger('click');
    expect(wrapper.find('form').exists()).toBe(true);
  });

  it('writes nothing to browser storage', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    mount(ProfilePage, { global });
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});
