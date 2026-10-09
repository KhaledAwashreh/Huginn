import { flushPromises, mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../src/api/apiError';
import ServiceOfferingListPage from '../../../src/features/configuration/offerings/pages/ServiceOfferingListPage.vue';
import IdealClientProfileListPage from '../../../src/features/configuration/ideal-client-profiles/pages/IdealClientProfileListPage.vue';

const state = vi.hoisted(() => ({
  removeOffering: vi.fn(),
  removeProfile: vi.fn(),
}));
vi.mock('../../../src/features/configuration/offerings/composables/useServiceOffering', () => ({
  useServiceOffering: () => ({
    list: {
      isPending: { value: false },
      isError: { value: false },
      isFetching: { value: false },
      data: {
        value: {
          items: [{ id: 'offering-id', name: 'Advisory', description: 'Launch support' }],
          limit: 100,
          offset: 0,
          has_more: false,
        },
      },
      refetch: vi.fn(),
    },
    remove: { isPending: { value: false }, mutateAsync: state.removeOffering },
  }),
}));
vi.mock(
  '../../../src/features/configuration/ideal-client-profiles/composables/useIdealClientProfile',
  () => ({
    useIdealClientProfile: () => ({
      list: {
        isPending: { value: false },
        isError: { value: false },
        isFetching: { value: false },
        data: {
          value: {
            items: [
              {
                id: 'icp-id',
                name: 'B2B SaaS',
                industries: [],
                company_sizes: [],
                geographies: [],
                exclusions: [],
              },
            ],
            limit: 100,
            offset: 0,
            has_more: false,
          },
        },
        refetch: vi.fn(),
      },
      remove: { isPending: { value: false }, mutateAsync: state.removeProfile },
    }),
  }),
);
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRouter: () => ({ push: vi.fn() }),
}));

beforeEach(() => {
  state.removeOffering.mockReset().mockRejectedValue(new ApiError(409, 'referenced', 'Conflict'));
  state.removeProfile.mockReset().mockRejectedValue(new ApiError(409, 'referenced', 'Conflict'));
});

const global = { plugins: [PrimeVue], stubs: { Dialog: { template: '<div><slot /></div>' } } };

describe('business definition lists', () => {
  it('keeps a referenced service offering visible and directs the user to strategies', async () => {
    const wrapper = mount(ServiceOfferingListPage, { global });
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Delete')
      ?.trigger('click');
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Delete offering')
      ?.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Advisory');
    expect(wrapper.text()).toContain('Update or remove that strategy reference first.');
    expect(state.removeOffering).toHaveBeenCalledWith('offering-id');
  });

  it('keeps a referenced ICP visible and directs the user to strategies', async () => {
    const wrapper = mount(IdealClientProfileListPage, { global });
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Delete')
      ?.trigger('click');
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Delete ICP')
      ?.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('B2B SaaS');
    expect(wrapper.text()).toContain('Update or remove that strategy reference first.');
    expect(state.removeProfile).toHaveBeenCalledWith('icp-id');
  });
});
