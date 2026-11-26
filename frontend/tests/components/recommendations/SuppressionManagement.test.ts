import { flushPromises, mount } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { beforeEach, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import SuppressionManagement from '../../../src/features/recommendations/components/SuppressionManagement.vue';
import type { SuppressionPage } from '../../../src/features/recommendations/models/prospecting';

const mocks = vi.hoisted(() => ({ cancel: vi.fn(), reverse: vi.fn() }));
vi.mock('../../../src/features/recommendations/api/cancelRecommendationPause', () => ({
  cancelRecommendationPause: mocks.cancel,
}));
vi.mock('../../../src/features/recommendations/api/reverseRecommendationRejection', () => ({
  reverseRecommendationRejection: mocks.reverse,
}));
const page: SuppressionPage = {
  offset: 0,
  limit: 25,
  has_more: true,
  items: [
    {
      company_id: 'company-1',
      company: {
        name: 'Northstar Labs',
        domain: 'northstar.example',
        business_sector: null,
        country: null,
        company_scale: null,
        company_status: null,
      },
      active_blocks: [
        {
          id: 'block-1',
          business_id: 'business-1',
          company_id: 'company-1',
          kind: 'rejection',
          created_at: '2026-11-01T00:00:00Z',
          effective_at: '2026-11-01T00:00:00Z',
          created_by_user_id: 'user-1',
          expires_at: null,
          cleared_at: null,
          cleared_by_user_id: null,
          reason: 'Wrong buyer',
          version: 4,
        },
      ],
      prospect: null,
      selection_state: {
        first_presented_at: null,
        cooldown_until: null,
        paused_until: null,
        paused_indefinitely: false,
        rejected: true,
        has_relationship: false,
        pending_delivery: false,
        uncertain_delivery: false,
      },
      selection_blockers: ['rejected'],
      read_at: '2026-11-14T00:00:00Z',
    },
  ],
};
function setup() {
  return mount(SuppressionManagement, {
    props: {
      identity: 'account-1:user-1:csrf',
      page,
      pending: false,
      failed: false,
      fetching: false,
      search: '',
      offset: 0,
      pageSize: 25,
    },
    global: {
      plugins: [
        PrimeVue,
        [
          VueQueryPlugin,
          { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
        ],
      ],
    },
  });
}
function buttonWithText(wrapper: ReturnType<typeof setup>, text: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text() === text);
  if (!button) throw new Error(`Button "${text}" was not found`);
  return button;
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'clear-key') });
});

it('shows the persistent rejection and clears only its versioned block', async () => {
  mocks.reverse.mockResolvedValue({
    suppression_block_id: 'block-1',
    block_version: 5,
    cleared_at: '2026-11-14T11:00:00Z',
    remaining_blockers: [],
  });
  const wrapper = setup();
  expect(wrapper.text()).toContain('persistent until reversed');
  expect(wrapper.text()).toContain('Wrong buyer');
  await buttonWithText(wrapper, 'Reverse rejection').trigger('click');
  await flushPromises();
  expect(mocks.reverse).toHaveBeenCalledWith('block-1', {
    expected_version: 4,
    request_key: 'clear-key',
  });
  expect(wrapper.text()).toContain('Rejection reversed');
  expect(wrapper.text()).toContain('Independent blocks remain unchanged');
});

it('passes server search and pagination actions to the owning workspace', async () => {
  const wrapper = setup();
  await wrapper
    .get('input[aria-label="Search suppressed companies by name or domain"]')
    .setValue('northstar.example');
  expect(wrapper.emitted('search')?.[0]).toEqual(['northstar.example']);
  await buttonWithText(wrapper, 'Next').trigger('click');
  expect(wrapper.emitted('next')).toHaveLength(1);
});

it('shows the mute removal result even after refresh removes the row', async () => {
  const wrapper = setup();
  const [item] = page.items;
  const block = item?.active_blocks[0];
  if (!item || !block) throw new Error('Expected a suppression fixture');
  await wrapper.setProps({
    page: {
      ...page,
      items: [{ ...item, active_blocks: [{ ...block, kind: 'pause' }] }],
    },
  });
  let resolve!: (result: object) => void;
  mocks.cancel.mockImplementationOnce(() => new Promise<object>((done) => (resolve = done)));

  await buttonWithText(wrapper, 'Remove mute').trigger('click');
  expect(buttonWithText(wrapper, 'Removing mute…').attributes('disabled')).toBeDefined();
  expect(wrapper.text()).not.toContain('Mute removed.');

  resolve({ suppression_block_id: 'block-1', block_version: 5 });
  await flushPromises();
  await wrapper.setProps({ page: { ...page, items: [] } });
  expect(wrapper.get('[role="status"]').text()).toBe('Mute removed.');
  expect(wrapper.text()).toContain('No matching active suppression decisions.');
  expect(mocks.cancel).toHaveBeenCalledTimes(1);

  await wrapper.setProps({ identity: 'another-account' });
  expect(wrapper.text()).not.toContain('Mute removed.');
});
