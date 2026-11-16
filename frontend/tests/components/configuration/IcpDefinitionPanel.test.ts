import { flushPromises, mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { beforeEach, expect, it, vi } from 'vitest';
import IcpDefinitionPanel from '@/features/configuration/ideal-client-profiles/components/IcpDefinitionPanel.vue';
import IdealClientProfileForm from '@/features/configuration/ideal-client-profiles/components/IdealClientProfileForm.vue';

const state = vi.hoisted(() => ({
  update: vi.fn(),
  create: vi.fn(),
  refetch: vi.fn(),
  setListItems: (items: unknown[]) => {
    state.listItems = items;
  },
  listItems: [] as unknown[],
  first: {
    id: 'first',
    name: 'First ICP',
    industries: [],
    company_sizes: [],
    geographies: [],
    exclusions: [],
  },
  second: {
    id: 'second',
    name: 'Second ICP',
    industries: [],
    company_sizes: [],
    geographies: [],
    exclusions: [],
  },
}));

vi.mock(
  '@/features/configuration/ideal-client-profiles/composables/useIdealClientProfile',
  async () => {
    const { ref } = await import('vue');
    const listData = ref<{ items: unknown[] }>({ items: [state.first, state.second] });
    state.listItems = listData.value.items;
    state.setListItems = (items) => {
      listData.value = { items };
      state.listItems = items;
    };
    return {
      useIdealClientProfile: (id?: () => string | undefined) => ({
        list: {
          isPending: { value: false },
          isError: { value: false },
          data: listData,
          refetch: state.refetch,
        },
        detail: {
          isPending: { value: false },
          isError: { value: false },
          data: { value: id?.() === 'second' ? state.second : undefined },
          refetch: async () => ({ isError: false, data: state.second }),
        },
        create: { mutateAsync: state.create },
        update: { mutateAsync: state.update },
      }),
    };
  },
);

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

const global = { stubs: { IdealClientProfileForm: true } };

beforeEach(() => {
  state.update.mockReset();
  state.create.mockReset();
  state.refetch.mockReset();
  state.setListItems([state.first, state.second]);
});

it('edits and refreshes the ICP selected from Profile', async () => {
  const wrapper = mount(IcpDefinitionPanel, {
    props: { clients: [], reactions: [], selectedIcpId: 'second' },
    global,
  });
  const form = wrapper.getComponent(IdealClientProfileForm);
  expect(form.props('initial').name).toBe('Second ICP');
  expect(await form.props('refreshSaved')()).toEqual(state.second);
  const draft = { ...form.props('initial'), name: 'Updated second ICP' };
  await form.props('save')(draft, { name: draft.name });
  expect(state.update).toHaveBeenCalledWith({ id: 'second', body: { name: draft.name } });
});

it('keeps an uncertain first-ICP draft when list refresh returns committed and concurrent rows', async () => {
  state.setListItems([]);
  state.create.mockRejectedValueOnce(new TypeError('the create response was lost'));
  const committed = { ...state.first, id: 'committed', name: 'New owner ICP' };
  const concurrent = { ...state.second, id: 'concurrent', name: 'Concurrent ICP' };
  state.refetch.mockImplementationOnce(async () => {
    const data = { items: [concurrent, committed] };
    state.setListItems(data.items);
    return { isError: false, data };
  });
  const wrapper = mount(IcpDefinitionPanel, {
    props: { clients: [], reactions: [] },
    global: { plugins: [PrimeVue] },
  });
  await flushPromises();
  await wrapper.get('#icp-name').setValue('New owner ICP');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('outcome is uncertain');
  expect(state.create).toHaveBeenCalledOnce();

  await wrapper.get('button[aria-label="Refresh saved data"]').trigger('click');
  await flushPromises();

  expect(state.listItems).toEqual([concurrent, committed]);
  expect(wrapper.findComponent(IdealClientProfileForm).props('existing')).toBe(false);
  expect((wrapper.get('#icp-name').element as HTMLInputElement).value).toBe('New owner ICP');
  expect(wrapper.text()).toContain('create result is still uncertain');
  expect((wrapper.get('button[type="submit"]').element as HTMLButtonElement).disabled).toBe(true);
  await wrapper.get('form').trigger('submit');
  expect(state.create).toHaveBeenCalledOnce();
  expect(state.update).not.toHaveBeenCalled();
});

it('hides client and feedback notes while they are empty', () => {
  const wrapper = mount(IcpDefinitionPanel, { props: { clients: [], reactions: [] }, global });
  expect(wrapper.text()).not.toContain('From your client list');
  expect(wrapper.text()).not.toContain('From your feedback');
  expect(wrapper.text()).not.toContain('Notes appear here');
});

it('shows the client and feedback notes passed by the composing level', () => {
  const wrapper = mount(IcpDefinitionPanel, {
    props: {
      clients: [
        {
          name: 'Example Commerce',
          idealExample: true,
          industry: 'Ecommerce',
          stage: '',
          size: '',
          location: '',
        },
      ],
      reactions: [
        {
          matchId: 'match-1',
          companyName: 'Example Company',
          kind: 'down' as const,
          reasonLabel: 'Wrong location',
        },
      ],
    },
    global,
  });
  expect(wrapper.text()).toContain('Example Commerce (Ecommerce)');
  expect(wrapper.text()).toContain('Example Company (Wrong location)');
});
