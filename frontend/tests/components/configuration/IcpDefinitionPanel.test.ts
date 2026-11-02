import { mount } from '@vue/test-utils';
import { expect, it, vi } from 'vitest';
import IcpDefinitionPanel from '@/features/configuration/ideal-client-profiles/components/IcpDefinitionPanel.vue';

vi.mock('@/features/configuration/ideal-client-profiles/composables/useIdealClientProfile', () => ({
  useIdealClientProfile: () => ({
    list: {
      isPending: { value: false },
      isError: { value: false },
      data: { value: { items: [] } },
    },
    create: {},
    update: {},
  }),
}));

const global = { stubs: { IdealClientProfileForm: { template: '<form />' } } };

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
