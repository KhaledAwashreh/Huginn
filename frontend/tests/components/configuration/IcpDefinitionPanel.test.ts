import { mount } from '@vue/test-utils';
import { expect, it, vi } from 'vitest';
import IcpDefinitionPanel from '@/features/configuration/ideal-client-profiles/components/IcpDefinitionPanel.vue';
import IdealClientProfileForm from '@/features/configuration/ideal-client-profiles/components/IdealClientProfileForm.vue';

const state = vi.hoisted(() => ({
  update: vi.fn(),
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

vi.mock('@/features/configuration/ideal-client-profiles/composables/useIdealClientProfile', () => ({
  useIdealClientProfile: (id?: () => string | undefined) => ({
    list: {
      isPending: { value: false },
      isError: { value: false },
      data: { value: { items: [state.first, state.second] } },
    },
    detail: {
      isPending: { value: false },
      isError: { value: false },
      data: { value: id?.() === 'second' ? state.second : undefined },
      refetch: async () => ({ isError: false, data: state.second }),
    },
    create: {},
    update: { mutateAsync: state.update },
  }),
}));

const global = { stubs: { IdealClientProfileForm: true } };

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
