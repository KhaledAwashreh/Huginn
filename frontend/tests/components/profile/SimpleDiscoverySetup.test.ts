import { mount, flushPromises } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { ref } from 'vue';
import PrimeVue from 'primevue/config';
import { beforeEach, expect, it, vi } from 'vitest';
import SimpleDiscoverySetup from '@/features/profile/components/SimpleDiscoverySetup.vue';

const state = vi.hoisted(() => ({
  strategies: null as unknown,
  references: null as unknown,
  save: vi.fn(),
  session: null as unknown,
}));
vi.mock('@/features/session/composables/useSession', () => ({
  useSession: () => ({ context: state.session }),
}));
vi.mock(
  '@/features/configuration/discovery-strategies/composables/useActiveDiscoveryStrategies',
  () => ({ useActiveDiscoveryStrategies: () => state.strategies }),
);
vi.mock('@/features/configuration/discovery-strategies/composables/useStrategyReferences', () => ({
  useStrategyReferences: () => state.references,
}));
vi.mock(
  '@/features/configuration/discovery-strategies/api/saveSingleDiscoveryConfiguration',
  () => ({ saveSingleDiscoveryConfiguration: state.save }),
);
const query = (data: unknown) => ({
  data: ref(data),
  isPending: ref(false),
  isError: ref(false),
  isFetching: ref(false),
  hasNextPage: ref(false),
  refetch: vi.fn(),
  fetchNextPage: vi.fn(),
});
const offering = {
  id: 'chosen-service',
  name: 'Chosen service',
  description: 'Chosen description',
};
const icp = {
  id: 'chosen-icp',
  name: 'Chosen ICP',
  industries: [],
  company_sizes: [],
  geographies: [],
  exclusions: [],
};
function setup() {
  return mount(SimpleDiscoverySetup, {
    global: {
      plugins: [PrimeVue, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: {
        OfferingReferenceSelect: {
          props: ['modelValue', 'items'],
          emits: ['update:modelValue'],
          template: `<select aria-label="Service offering" :value="modelValue" @change="$emit('update:modelValue', $event.target.value)"><option value=""></option><option v-for="item in items" :value="item.id">{{ item.name }}</option></select>`,
        },
        IcpReferenceSelect: {
          props: ['modelValue', 'items'],
          emits: ['update:modelValue'],
          template: `<select aria-label="ICP" :value="modelValue" @change="$emit('update:modelValue', $event.target.value)"><option value=""></option><option v-for="item in items" :value="item.id">{{ item.name }}</option></select>`,
        },
      },
    },
  });
}
beforeEach(() => {
  state.session = ref({
    account_id: 'a',
    user_id: 'u',
    csrf_token: 'c',
    simple_discovery_enabled: true,
  });
  state.strategies = { strategies: query([]), singleStrategy: ref(null) };
  state.references = {
    offerings: query(undefined),
    icps: query(undefined),
    offeringItems: ref([offering]),
    icpItems: ref([icp]),
    selectedOffering: query(undefined),
    selectedIcp: query(undefined),
  };
  state.save.mockReset();
});
it('requires an explicit pair save and sends only selected IDs', async () => {
  const wrapper = setup();
  expect(state.save).not.toHaveBeenCalled();
  await wrapper.get('select[aria-label="Service offering"]').setValue(offering.id);
  await wrapper.get('select[aria-label="ICP"]').setValue(icp.id);
  expect(state.save).not.toHaveBeenCalled();
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(state.save).toHaveBeenCalledWith({
    service_offering_id: offering.id,
    ideal_client_profile_id: icp.id,
  });
});
it('displays only the chosen references and edits that exact ICP', async () => {
  (state.strategies as { singleStrategy: { value: unknown } }).singleStrategy.value = {
    id: 's',
    service_offering_id: offering.id,
    ideal_client_profile_id: icp.id,
  };
  (state.references as { offeringItems: { value: unknown[] } }).offeringItems.value.push({
    id: 'hidden',
    name: 'Hidden service',
  });
  const wrapper = setup();
  expect(wrapper.text()).toContain(offering.name);
  expect(wrapper.text()).toContain(icp.name);
  expect(wrapper.text()).not.toContain('Hidden service');
  expect(wrapper.find('form').exists()).toBe(false);
  await wrapper.get('button[aria-label="Edit ICP definition"]').trigger('click');
  expect(wrapper.emitted('editIcp')).toEqual([[icp.id]]);
});
it('retains the selected draft when saving fails', async () => {
  state.save.mockRejectedValue(new Error('Save failed'));
  const wrapper = setup();
  await wrapper.get('select[aria-label="Service offering"]').setValue(offering.id);
  await wrapper.get('select[aria-label="ICP"]').setValue(icp.id);
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain('could not be saved');
  expect((wrapper.get('select[aria-label="ICP"]').element as HTMLSelectElement).value).toBe(icp.id);
});
