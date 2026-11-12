import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';
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
  saveProfile: vi.fn(),
  offerings: undefined as unknown,
  servicePage: vi.fn(),
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
  useProfessionalProfile: () => ({
    profile: state.profile,
    save: { mutateAsync: state.saveProfile },
  }),
}));
vi.mock('@/features/configuration/offerings/composables/useServiceOffering', () => ({
  useServiceOffering: (_id: undefined, offset: MaybeRefOrGetter<number> = 0, limit = 100) => ({
    list: state.servicePage(offset, limit) ?? state.offerings,
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
  state.saveProfile.mockReset();
  state.offerings = query(page([service]));
  state.servicePage.mockReset();
  state.icps = query(page([]));
  state.create.mockReset();
  state.update.mockReset();
  state.remove.mockReset();
});

it('preserves an existing skill containing a comma when adding another skill', async () => {
  state.profile = query({ ...profileData, skills: [{ name: 'Research, design' }] });
  const wrapper = mount(ProfilePage, { global });
  await button(wrapper, 'Edit skills').trigger('click');
  await button(wrapper, 'Add skill').trigger('click');
  await wrapper.get('#skill-1').setValue('Strategy');
  await wrapper.get('form').trigger('submit');
  expect(state.saveProfile).toHaveBeenCalledWith({
    skills: [{ name: 'Research, design' }, { name: 'Strategy' }],
  });
});

it('does not write an untouched About draft over a refreshed summary', async () => {
  const data = ref(profileData);
  state.profile = { ...query(profileData), data };
  const wrapper = mount(ProfilePage, { global });
  await button(wrapper, 'Edit about your business').trigger('click');
  data.value = { ...profileData, professional_summary: 'A newer saved summary.' };
  await wrapper.get('form').trigger('submit');
  expect(state.saveProfile).not.toHaveBeenCalled();
});

it('keeps an edited About draft until replacing a newer summary is confirmed', async () => {
  const data = ref(profileData);
  state.profile = { ...query(profileData), data };
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const wrapper = mount(ProfilePage, { global });
  await button(wrapper, 'Edit about your business').trigger('click');
  await wrapper.get('#about-summary').setValue('My edited summary');
  data.value = { ...profileData, professional_summary: 'A newer saved summary.' };
  await wrapper.get('form').trigger('submit');
  expect(confirm).toHaveBeenCalled();
  expect(state.saveProfile).not.toHaveBeenCalled();
  expect((wrapper.get('#about-summary').element as HTMLTextAreaElement).value).toBe(
    'My edited summary',
  );
  confirm.mockReturnValue(true);
  await wrapper.get('form').trigger('submit');
  expect(state.saveProfile).toHaveBeenCalledWith({ professional_summary: 'My edited summary' });
});

it('does not write untouched skills over refreshed skills', async () => {
  const data = ref({ ...profileData, skills: [{ name: 'Design' }] });
  state.profile = { ...query(data.value), data };
  const wrapper = mount(ProfilePage, { global });
  await button(wrapper, 'Edit skills').trigger('click');
  data.value = { ...data.value, skills: [{ name: 'Strategy' }] };
  await wrapper.get('form').trigger('submit');
  expect(state.saveProfile).not.toHaveBeenCalled();
});

it('requires confirmation before replacing refreshed skills with an edited draft', async () => {
  const data = ref({ ...profileData, skills: [{ name: 'Design' }] });
  state.profile = { ...query(data.value), data };
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const wrapper = mount(ProfilePage, { global });
  await button(wrapper, 'Edit skills').trigger('click');
  await wrapper.get('#skill-0').setValue('Research');
  data.value = { ...data.value, skills: [{ name: 'Strategy' }] };
  await wrapper.get('form').trigger('submit');
  expect(confirm).toHaveBeenCalled();
  expect(state.saveProfile).not.toHaveBeenCalled();
  confirm.mockReturnValue(true);
  await wrapper.get('form').trigger('submit');
  expect(state.saveProfile).toHaveBeenCalledWith({ skills: [{ name: 'Research' }] });
});

it('keeps an About draft and requires a refresh after an uncertain save', async () => {
  const profile = query(profileData);
  state.profile = profile;
  state.saveProfile.mockRejectedValueOnce(new TypeError('Failed to fetch'));
  profile.refetch.mockResolvedValue({ isError: false, data: profileData });
  const wrapper = mount(ProfilePage, { global });
  await button(wrapper, 'Edit about your business').trigger('click');
  await wrapper.get('#about-summary').setValue('An updated summary');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('The save outcome is unknown.');
  expect(wrapper.text()).not.toContain('Failed to fetch');
  await wrapper.get('form').trigger('submit');
  expect(state.saveProfile).toHaveBeenCalledOnce();

  await button(wrapper, 'Refresh saved profile').trigger('click');
  await flushPromises();
  expect(profile.refetch).toHaveBeenCalledOnce();
  expect((wrapper.get('#about-summary').element as HTMLTextAreaElement).value).toBe(
    'An updated summary',
  );
  await wrapper.get('form').trigger('submit');
  expect(state.saveProfile).toHaveBeenCalledTimes(2);
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

  it('updates only the edited service fields', async () => {
    const wrapper = mount(ProfilePage, { global });
    await openService(wrapper);
    await wrapper.get('#item-name').setValue('Product advising');
    await wrapper.get('form').trigger('submit');
    expect(state.update).toHaveBeenCalledWith({
      id: service.id,
      body: { name: 'Product advising' },
    });
  });

  it('does not update an unchanged service', async () => {
    const wrapper = mount(ProfilePage, { global });
    await openService(wrapper);
    await wrapper.get('form').trigger('submit');
    expect(state.update).not.toHaveBeenCalled();
  });

  it('updates only the description when the service name is untouched', async () => {
    const wrapper = mount(ProfilePage, { global });
    await openService(wrapper);
    await wrapper.get('#item-description').setValue('Project advice.');
    await wrapper.get('form').trigger('submit');
    expect(state.update).toHaveBeenCalledWith({
      id: service.id,
      body: { description: 'Project advice.' },
    });
  });

  it('reports a network failure as uncertain and requires a refresh before retrying', async () => {
    state.update.mockRejectedValue(new TypeError('Failed to fetch'));
    const offerings = query(page([service]));
    offerings.refetch.mockResolvedValue({ isError: false, data: page([service]) });
    state.offerings = offerings;
    const wrapper = mount(ProfilePage, { global });
    await openService(wrapper);
    await wrapper.get('#item-name').setValue('Product advising');
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

it('browses services beyond the first API page', async () => {
  const nextService = { id: 'service-101', name: 'Implementation', description: 'Project work.' };
  state.servicePage.mockImplementation((offset: MaybeRefOrGetter<number>, limit: number) => ({
    ...query(undefined),
    data: computed(() => {
      const current = toValue(offset);
      return {
        items: current === 0 ? [service] : [nextService],
        limit,
        offset: current,
        has_more: current === 0,
      };
    }),
  }));
  const wrapper = mount(ProfilePage, { global });
  expect(wrapper.text()).toContain('Advising');
  expect(button(wrapper, 'Previous').attributes('disabled')).toBeDefined();
  await button(wrapper, 'Next').trigger('click');
  expect(wrapper.text()).toContain('Implementation');
  expect(wrapper.get('nav[aria-label="Service pages"]').text()).toContain('Page 2');
  expect(wrapper.text()).not.toContain('Advising');
  expect(button(wrapper, 'Next').attributes('disabled')).toBeDefined();

  await button(wrapper, 'Previous').trigger('click');
  expect(wrapper.text()).toContain('Advising');
  expect(wrapper.text()).not.toContain('Implementation');
});

it('keeps an unsaved About draft when the user declines to leave Profile', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/profile', component: ProfilePage },
      { path: '/matches', component: { template: '<div>Matches</div>' } },
    ],
  });
  await router.push('/profile');
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const wrapper = mount(RouterView, { global: { ...global, plugins: [PrimeVue, router] } });
  await button(wrapper, 'Edit about your business').trigger('click');
  await wrapper.get('#about-summary').setValue('Unsaved summary');

  const unload = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(unload);
  expect(unload.defaultPrevented).toBe(true);

  await router.push('/matches');

  expect(confirm).toHaveBeenCalledOnce();
  expect(router.currentRoute.value.path).toBe('/profile');
  expect((wrapper.get('#about-summary').element as HTMLTextAreaElement).value).toBe(
    'Unsaved summary',
  );

  confirm.mockReturnValue(true);
  await router.push('/matches');
  expect(router.currentRoute.value.path).toBe('/matches');
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
