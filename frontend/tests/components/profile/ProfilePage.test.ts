import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';
import { ApiError } from '@/api/apiError';
import ProfilePage from '@/features/profile/pages/ProfilePage.vue';
import { openSettingsKey } from '@/shared/navigation/settingsSections';

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
const businessProfileData = {
  id: 'business-1',
  owner_user_id: 'user-1',
  name: null,
  tagline: null,
  website: null,
  location: null,
  description: null,
  capabilities: null,
  created_at: '2026-10-09T12:00:00Z',
  updated_at: '2026-10-09T12:00:00Z',
};

const state = vi.hoisted(() => ({
  profile: undefined as unknown,
  saveProfile: vi.fn(),
  business: undefined as unknown,
  saveBusiness: vi.fn(),
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
vi.mock('@/features/profile/composables/useBusinessProfile', () => ({
  useBusinessProfile: () => ({
    business: state.business,
    save: { mutateAsync: state.saveBusiness, isPending: { value: false } },
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
    RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
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
  state.business = query(businessProfileData);
  state.saveProfile.mockReset();
  state.saveBusiness.mockReset();
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

it('enables editing for Business fields now backed by the Business API', () => {
  const wrapper = mount(ProfilePage, { global });
  expect(button(wrapper, 'Edit business details').attributes('disabled')).toBeUndefined();
});

it('keeps the personal professional summary separate from Business description', () => {
  state.business = query({
    ...businessProfileData,
    name: 'Independent product studio',
    description: 'Business description from the Business API.',
  });
  state.profile = query({
    ...profileData,
    professional_summary: 'Personal professional summary from the User profile.',
  });
  const wrapper = mount(ProfilePage, { global });

  expect(wrapper.get('[aria-label="Your business"]').text()).toContain(
    'Independent product studio',
  );
  expect(wrapper.text()).toContain('Business description from the Business API.');
  expect(wrapper.text()).toContain('Personal professional summary from the User profile.');
  expect(button(wrapper, 'Edit business description').attributes('disabled')).toBeUndefined();
  expect(button(wrapper, 'Edit professional summary').attributes('disabled')).toBeUndefined();
});

it('labels the User professional-profile timestamp instead of the Business timestamp', () => {
  const userUpdatedAt = '2025-04-03T00:00:00Z';
  const businessUpdatedAt = '2026-10-11T00:00:00Z';
  state.profile = query({ ...profileData, updated_at: userUpdatedAt });
  state.business = query({ ...businessProfileData, updated_at: businessUpdatedAt });
  const wrapper = mount(ProfilePage, { global });

  expect(wrapper.get('.last-edited').text()).toBe(
    `Professional profile updated ${new Date(userUpdatedAt).toLocaleDateString()}`,
  );
  expect(wrapper.get('.last-edited').text()).not.toContain(
    new Date(businessUpdatedAt).toLocaleDateString(),
  );
});

it('does not write an untouched About draft over a refreshed summary', async () => {
  const data = ref(profileData);
  state.profile = { ...query(profileData), data };
  const wrapper = mount(ProfilePage, { global });
  await button(wrapper, 'Edit professional summary').trigger('click');
  data.value = { ...profileData, professional_summary: 'A newer saved summary.' };
  await wrapper.get('form').trigger('submit');
  expect(state.saveProfile).not.toHaveBeenCalled();
});

it('keeps an edited About draft until replacing a newer summary is confirmed', async () => {
  const data = ref(profileData);
  state.profile = { ...query(profileData), data };
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const wrapper = mount(ProfilePage, { global });
  await button(wrapper, 'Edit professional summary').trigger('click');
  await wrapper.get('#personal-summary').setValue('My edited summary');
  data.value = { ...profileData, professional_summary: 'A newer saved summary.' };
  await wrapper.get('form').trigger('submit');
  expect(confirm).toHaveBeenCalled();
  expect(state.saveProfile).not.toHaveBeenCalled();
  expect((wrapper.get('#personal-summary').element as HTMLTextAreaElement).value).toBe(
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
  await button(wrapper, 'Edit professional summary').trigger('click');
  await wrapper.get('#personal-summary').setValue('An updated summary');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('The save outcome is unknown.');
  expect(wrapper.text()).not.toContain('Failed to fetch');
  await wrapper.get('form').trigger('submit');
  expect(state.saveProfile).toHaveBeenCalledOnce();

  await button(wrapper, 'Refresh saved profile').trigger('click');
  await flushPromises();
  expect(profile.refetch).toHaveBeenCalledOnce();
  expect((wrapper.get('#personal-summary').element as HTMLTextAreaElement).value).toBe(
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

it('explains disabled profile actions with visible descriptions referenced by the controls', () => {
  const wrapper = mount(ProfilePage, { global });
  const gated = wrapper.findAll('button[disabled]');
  const profileActions = gated.filter((control) =>
    ['Edit business details', 'Add a leader', 'Add a client', 'Add a link'].includes(
      control.attributes('aria-label') ?? '',
    ),
  );
  expect(profileActions.length).toBeGreaterThan(0);
  for (const control of profileActions) {
    const descriptionId = control.attributes('aria-describedby');
    expect(descriptionId).toBeTruthy();
    const description = wrapper.find(`#${descriptionId}`);
    expect(description.exists()).toBe(true);
    expect(description.text().trim()).not.toBe('');
  }
});

it('keeps availability explanation IDs unique across Profile instances', () => {
  const wrapper = mount(
    {
      components: { ProfilePage },
      template: '<main><ProfilePage /><ProfilePage /></main>',
    },
    { global },
  );
  const reasonIds = wrapper
    .findAll('.availability-reason')
    .map((reason) => reason.attributes('id'));
  expect(new Set(reasonIds).size).toBe(reasonIds.length);
  for (const control of wrapper.findAll('[aria-describedby]')) {
    const id = control.attributes('aria-describedby');
    expect(id).toBeTruthy();
    expect(wrapper.findAll(`#${id}`)).toHaveLength(1);
  }
});

it('opens Settings for the chosen ICP without adding standalone Profile routes', async () => {
  state.icps = query(
    page([
      {
        id: 'first',
        name: 'First ICP',
        industries: [],
        company_sizes: [],
        geographies: [],
        exclusions: [],
      },
      {
        id: 'second',
        name: 'Second ICP',
        industries: [],
        company_sizes: [],
        geographies: [],
        exclusions: [],
      },
    ]),
  );
  const openSettings = vi.fn();
  const wrapper = mount(ProfilePage, {
    global: {
      ...global,
      provide: { [openSettingsKey as symbol]: openSettings },
    },
  });

  expect(wrapper.find('a[href="/icps"]').exists()).toBe(false);
  expect(wrapper.find('a[href="/strategies"]').exists()).toBe(false);
  expect(wrapper.findAll('h2').map((heading) => heading.text())).not.toContain(
    'Discovery strategies',
  );
  expect(wrapper.text()).not.toContain(
    'Choose which services and ICP definitions to use for future discovery runs.',
  );
  await wrapper.findAll('.icp-tile')[1]?.trigger('click');
  expect(openSettings).toHaveBeenCalledWith('icp', 'second');
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

  it('retains an uncertain service create after refreshing a page that cannot confirm it', async () => {
    state.create.mockRejectedValue(new TypeError('Failed to fetch'));
    const offerings = query({ ...page([service]), has_more: true });
    offerings.refetch.mockResolvedValue({
      isError: false,
      data: { ...page([service]), has_more: true },
    });
    state.offerings = offerings;
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const wrapper = mount(ProfilePage, { global });
    await button(wrapper, 'Add a service').trigger('click');
    await wrapper.get('#item-name').setValue('Implementation');
    await wrapper.get('#item-description').setValue('A carefully drafted service description.');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    await button(wrapper, 'Refresh services').trigger('click');
    await flushPromises();
    expect((wrapper.get('#item-name').element as HTMLInputElement).value).toBe('Implementation');
    expect((wrapper.get('#item-description').element as HTMLTextAreaElement).value).toBe(
      'A carefully drafted service description.',
    );
    expect(wrapper.text()).toContain('Your new service is still unconfirmed.');
    expect(wrapper.findAll('button').some((item) => item.text() === 'Save')).toBe(false);
    await wrapper.get('form').trigger('submit');
    expect(state.create).toHaveBeenCalledOnce();
    await button(wrapper, 'Cancel').trigger('click');
    expect(confirm).toHaveBeenCalled();
    expect(wrapper.find('form').exists()).toBe(true);
    confirm.mockReturnValue(true);
    await button(wrapper, 'Cancel').trigger('click');
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
  await button(wrapper, 'Edit professional summary').trigger('click');
  await wrapper.get('#personal-summary').setValue('Unsaved summary');

  const unload = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(unload);
  expect(unload.defaultPrevented).toBe(true);

  await router.push('/matches');

  expect(confirm).toHaveBeenCalledOnce();
  expect(router.currentRoute.value.path).toBe('/profile');
  expect((wrapper.get('#personal-summary').element as HTMLTextAreaElement).value).toBe(
    'Unsaved summary',
  );

  confirm.mockReturnValue(true);
  await router.push('/matches');
  expect(router.currentRoute.value.path).toBe('/matches');
});

it('delegates Profile navigation and unload guards to a Business details draft', async () => {
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
  await button(wrapper, 'Edit business details').trigger('click');
  await wrapper.get('#business-description').setValue('Unsaved Business draft');

  const unload = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(unload);
  expect(unload.defaultPrevented).toBe(true);

  await router.push('/matches');
  await flushPromises();
  expect(router.currentRoute.value.path).toBe('/profile');
  expect((wrapper.get('#business-description').element as HTMLTextAreaElement).value).toBe(
    'Unsaved Business draft',
  );
  expect(confirm).toHaveBeenCalledOnce();

  confirm.mockReturnValue(true);
  await router.push('/matches');
  await flushPromises();
  expect(router.currentRoute.value.path).toBe('/matches');
});

it('keeps Business draft values when the Profile route guard rejects navigation', async () => {
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
  await button(wrapper, 'Edit business details').trigger('click');
  await wrapper.get('#business-description').setValue('Retained business draft');
  await router.push('/matches');
  await flushPromises();

  expect(router.currentRoute.value.path).toBe('/profile');
  expect((wrapper.get('#business-description').element as HTMLTextAreaElement).value).toBe(
    'Retained business draft',
  );
  expect(confirm).toHaveBeenCalledOnce();
});

describe('features awaiting a backend', () => {
  it('disables them with honest copy and leaves API-backed items working', async () => {
    const wrapper = mount(ProfilePage, { global });
    expect(wrapper.text()).toContain('Your business');
    expect(wrapper.text()).toContain('Add a short description of your business.');
    expect(wrapper.text()).toContain('About your business');
    expect(wrapper.text()).toContain('Professional summary');
    expect(wrapper.text()).toContain('Client list is coming soon.');
    expect(wrapper.text()).toContain('Links are coming soon.');
    expect(wrapper.text()).not.toContain('Links and files');
    expect(wrapper.find('input[type="file"]').exists()).toBe(false);
    const leader = wrapper.findAll('button').find((item) => item.text().includes('Bob Browser'));
    for (const control of [
      button(wrapper, 'Add a leader'),
      button(wrapper, 'Add a client'),
      button(wrapper, 'Add a link'),
      leader,
    ]) {
      expect(control?.attributes('disabled')).toBeDefined();
      expect(control?.attributes('aria-describedby')).toBeTruthy();
    }
    expect(leader?.text()).toContain('Bob Browser');
    expect(leader?.text()).not.toContain('Founder');

    expect(button(wrapper, 'Edit business details').attributes('disabled')).toBeUndefined();
    for (const label of [
      'Edit business description',
      'Edit professional summary',
      'Edit skills',
      'Add a service',
    ]) {
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
