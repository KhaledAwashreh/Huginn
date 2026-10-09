import { computed, defineComponent, ref } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { afterEach, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/apiError';
import { useStrategyReferences } from '@/features/configuration/discovery-strategies/composables/useStrategyReferences';
const mocks = vi.hoisted(() => ({
  listOfferings: vi.fn(),
  getOffering: vi.fn(),
  listIcps: vi.fn(),
  getIcp: vi.fn(),
}));
vi.mock('@/features/session/composables/useSession', () => ({
  useSession: () => ({
    context: { value: { account_id: 'owner-account', user_id: 'owner-user' } },
  }),
}));
vi.mock('@/features/configuration/offerings/api/listServiceOfferings', () => ({
  listServiceOfferings: mocks.listOfferings,
}));
vi.mock('@/features/configuration/offerings/api/getServiceOffering', () => ({
  getServiceOffering: mocks.getOffering,
}));
vi.mock('@/features/configuration/ideal-client-profiles/api/listIdealClientProfiles', () => ({
  listIdealClientProfiles: mocks.listIcps,
}));
vi.mock('@/features/configuration/ideal-client-profiles/api/getIdealClientProfile', () => ({
  getIdealClientProfile: mocks.getIcp,
}));
afterEach(() => vi.resetAllMocks());
it('loads bounded pages beyond 100 and preserves the selected owner item', async () => {
  mocks.listOfferings.mockImplementation((offset: number) =>
    Promise.resolve({
      offset,
      limit: 100,
      has_more: offset === 0,
      items: Array.from({ length: offset === 0 ? 100 : 1 }, (_, index) => ({
        id: `offering-${offset + index}`,
        name: `Offering ${offset + index}`,
      })),
    }),
  );
  mocks.listIcps.mockResolvedValue({ offset: 0, limit: 100, has_more: false, items: [] });
  mocks.getOffering.mockResolvedValue({ id: 'selected-150', name: 'Saved selection' });
  mocks.getIcp.mockRejectedValue(new ApiError(404, 'not_found', 'Unavailable'));
  const selected = ref('selected-150');
  const harness = defineComponent({
    setup() {
      const state = useStrategyReferences(selected, 'removed-icp');
      return { state, count: computed(() => state.offeringItems.value.length) };
    },
    template: '<button @click="state.offerings.fetchNextPage()">{{count}}</button>',
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = mount(harness, {
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  });
  await flushPromises();
  expect(wrapper.text()).toBe('100');
  expect(mocks.listOfferings).toHaveBeenCalledWith(0, 100, expect.any(AbortSignal));
  expect(mocks.getOffering).toHaveBeenCalledWith('selected-150', expect.any(AbortSignal));
  expect(mocks.getIcp).toHaveBeenCalledWith('removed-icp', expect.any(AbortSignal));
  await wrapper.get('button').trigger('click');
  await flushPromises();
  expect(wrapper.text()).toBe('101');
  expect(mocks.listOfferings).toHaveBeenCalledWith(100, 100, expect.any(AbortSignal));
  expect(selected.value).toBe('selected-150');
  expect(
    client
      .getQueryCache()
      .getAll()
      .every(
        (query) =>
          query.queryKey.includes('owner-account') && query.queryKey.includes('owner-user'),
      ),
  ).toBe(true);
  expect(mocks.getIcp).toHaveBeenCalledOnce();
  client.clear();
});
