import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import TargetUserSelect from '@/features/matchmaking/components/TargetUserSelect.vue';

const { useTargetUsersMock } = vi.hoisted(() => ({ useTargetUsersMock: vi.fn() }));
vi.mock('@/features/matchmaking/composables/useTargetUsers', () => ({
  useTargetUsers: useTargetUsersMock,
}));

const user = {
  id: '1f891e25-047d-4c76-bf6d-701c28e47b31',
  username: 'northstar',
  first_name: 'North',
  last_name: 'Star',
  has_active_strategies: true,
};

describe('matchmaking target selection', () => {
  it('keeps an off-page selected identity visible while searching and paging beyond the first page', async () => {
    let currentSearch = () => '';
    let currentOffset = () => 100;
    useTargetUsersMock.mockImplementation((search: () => string, offset: () => number) => {
      currentSearch = search;
      currentOffset = offset;
      return {
        pageSize: 20,
        users: {
          data: { value: { items: [user], has_more: true, total_eligible_count: 121 } },
          isPending: { value: false },
          isError: { value: false },
          isFetching: { value: false },
          refetch: vi.fn(),
        },
      };
    });
    const wrapper = mount(TargetUserSelect, {
      props: { modelValue: user },
      global: { plugins: [PrimeVue] },
    });

    expect(wrapper.text()).toContain('Selected: northstar');
    expect(wrapper.text()).toContain('121 users are currently eligible');
    await wrapper.get('input[type="search"]').setValue('north');
    expect(currentSearch()).toBe('north');
    expect(currentOffset()).toBe(0);
    await wrapper.get('button[aria-pressed="true"]').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([user]);
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'More users')
      ?.trigger('click');
    expect(currentOffset()).toBe(20);
    expect(wrapper.text()).toContain(user.id);
  });
});
