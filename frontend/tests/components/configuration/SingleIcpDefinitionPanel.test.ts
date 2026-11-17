import { flushPromises, mount } from '@vue/test-utils';
import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue';
import PrimeVue from 'primevue/config';
import { beforeEach, expect, it, vi } from 'vitest';
import SingleIcpDefinitionPanel from '@/features/configuration/ideal-client-profiles/components/SingleIcpDefinitionPanel.vue';
import IcpDefinitionPanel from '@/features/configuration/ideal-client-profiles/components/IcpDefinitionPanel.vue';
const state = vi.hoisted(() => ({
  active: null as unknown,
  icps: null as unknown,
  records: [] as {
    id: string;
    name: string;
    industries: [];
    company_sizes: [];
    geographies: [];
    exclusions: [];
  }[],
  create: vi.fn(),
  update: vi.fn(),
}));
vi.mock(
  '@/features/configuration/discovery-strategies/composables/useActiveDiscoveryStrategies',
  () => ({ useActiveDiscoveryStrategies: () => state.active }),
);
vi.mock('@/features/configuration/ideal-client-profiles/composables/useIdealClientProfile', () => ({
  useIdealClientProfile: (id?: MaybeRefOrGetter<string | undefined>) => ({
    list: state.icps,
    detail: {
      data: computed(() => state.records.find((item) => item.id === toValue(id))),
      isPending: ref(false),
      isError: ref(false),
      refetch: vi.fn(),
    },
    create: { mutateAsync: state.create },
    update: { mutateAsync: state.update },
  }),
}));
vi.mock(
  '@/features/configuration/ideal-client-profiles/composables/useConfigurationOptions',
  () => ({
    useConfigurationOptions: () => ({
      data: ref({ industries: [], countries: [], company_sizes: [] }),
      isPending: ref(false),
      isError: ref(false),
    }),
  }),
);
const query = (data: unknown) => ({
  data: ref(data),
  isPending: ref(false),
  isError: ref(false),
  refetch: vi.fn(),
});
function setup(realPanel = false) {
  return mount(SingleIcpDefinitionPanel, {
    props: { clients: [], reactions: [] },
    global: {
      plugins: [PrimeVue],
      stubs: {
        IcpDefinitionPanel: !realPanel,
        RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
      },
    },
  });
}
beforeEach(() => {
  state.records = [];
  state.create.mockReset();
  state.update.mockReset();
  state.active = { strategies: query([]), singleStrategy: ref(null) };
  state.icps = query({ items: [{ id: 'first' }, { id: 'chosen' }], has_more: false });
});
it('pins Settings to the chosen ICP even when another legacy ICP is first', () => {
  (state.active as { singleStrategy: { value: unknown } }).singleStrategy.value = {
    ideal_client_profile_id: 'chosen',
  };
  const wrapper = setup();
  expect(wrapper.getComponent(IcpDefinitionPanel).props('selectedIcpId')).toBe('chosen');
});
it('requires Profile setup for ambiguity rather than editing the first legacy ICP', () => {
  const wrapper = setup();
  expect(wrapper.findComponent(IcpDefinitionPanel).exists()).toBe(false);
  expect(wrapper.get('a[href="/profile"]').text()).toBe('Set up discovery in Profile');
});
it('reuses the existing create form only when there are no saved ICPs', () => {
  state.icps = query({ items: [], has_more: false });
  const wrapper = setup();
  expect(wrapper.getComponent(IcpDefinitionPanel).props('selectedIcpId')).toBeUndefined();
});

it('keeps the real first-ICP editor mounted while a successful create refreshes the list', async () => {
  const list = query({ items: [], has_more: false });
  state.icps = list;
  const saved = {
    id: 'created',
    name: 'New client profile',
    industries: [] as [],
    company_sizes: [] as [],
    geographies: [] as [],
    exclusions: [] as [],
  };
  state.create.mockImplementation(async () => {
    state.records = [saved];
    list.data.value = { items: [saved], has_more: false };
    await flushPromises();
    return saved;
  });
  const wrapper = setup(true);
  await wrapper.get('#icp-name').setValue(saved.name);
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.findComponent(IcpDefinitionPanel).exists()).toBe(true);
  expect((wrapper.get('#icp-name').element as HTMLInputElement).value).toBe(saved.name);
  state.update.mockResolvedValue({ ...saved, name: 'Edited after create' });
  await wrapper.get('#icp-name').setValue('Edited after create');
  await wrapper.get('form').trigger('submit');
  expect(state.create).toHaveBeenCalledOnce();
  expect(state.update).toHaveBeenCalledWith({
    id: saved.id,
    body: { name: 'Edited after create' },
  });
});

it('retains uncertain create intent and draft when refresh discovers committed and concurrent ICPs', async () => {
  const list = query({ items: [], has_more: false });
  state.icps = list;
  const committed = {
    id: 'committed',
    name: 'My profile',
    industries: [] as [],
    company_sizes: [] as [],
    geographies: [] as [],
    exclusions: [] as [],
  };
  const concurrent = { ...committed, id: 'concurrent', name: 'Concurrent profile' };
  state.create.mockRejectedValueOnce(new TypeError('Response lost'));
  list.refetch.mockImplementation(async () => {
    state.records = [concurrent, committed];
    const data = { items: [concurrent, committed], has_more: false };
    list.data.value = data;
    await flushPromises();
    return { isError: false, data };
  });
  const wrapper = setup(true);
  await wrapper.get('#icp-name').setValue(committed.name);
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('outcome is uncertain');
  await wrapper.get('button[aria-label="Refresh saved data"]').trigger('click');
  await flushPromises();
  expect(wrapper.findComponent(IcpDefinitionPanel).exists()).toBe(true);
  expect((wrapper.get('#icp-name').element as HTMLInputElement).value).toBe(committed.name);
  expect(wrapper.text()).toContain('create result is still uncertain');
  expect((wrapper.get('button[type="submit"]').element as HTMLButtonElement).disabled).toBe(true);
  await wrapper.get('form').trigger('submit');
  expect(state.create).toHaveBeenCalledOnce();
  expect(state.update).not.toHaveBeenCalled();
});

it('keeps an admitted edit on its exact ICP while the active configuration refreshes', async () => {
  const active = state.active as {
    singleStrategy: { value: { ideal_client_profile_id: string } | null };
    strategies: { isError: { value: boolean } };
  };
  active.singleStrategy.value = { ideal_client_profile_id: 'chosen' };
  const wrapper = setup();
  active.singleStrategy.value = { ideal_client_profile_id: 'replacement' };
  await wrapper.vm.$nextTick();
  expect(wrapper.getComponent(IcpDefinitionPanel).props('selectedIcpId')).toBe('chosen');
  active.strategies.isError.value = true;
  await wrapper.vm.$nextTick();
  expect(wrapper.getComponent(IcpDefinitionPanel).props('selectedIcpId')).toBe('chosen');
});
