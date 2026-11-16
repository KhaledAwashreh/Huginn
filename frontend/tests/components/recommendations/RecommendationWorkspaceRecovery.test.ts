import { flushPromises, mount } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { beforeEach, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import { createRouter, createMemoryHistory, RouterView } from 'vue-router';
import { defineComponent, h } from 'vue';
import RecommendationsPage from '../../../src/features/recommendations/pages/RecommendationsPage.vue';
import type {
  RecommendationPage,
  RecommendationView,
} from '../../../src/features/recommendations/models/prospecting';

const pageHost = defineComponent({ setup: () => () => h(RouterView) });

const mocks = vi.hoisted(() => ({
  session: { value: null as unknown },
  list: vi.fn(),
  preferences: vi.fn(),
  strategies: vi.fn(),
  suppressions: vi.fn(),
  save: vi.fn(),
  get: vi.fn(),
  serverCommitted: false,
}));
vi.mock('../../../src/features/session/composables/useSession', () => ({
  useSession: () => ({ context: mocks.session }),
}));
vi.mock('../../../src/features/recommendations/api/listRecommendations', () => ({
  listRecommendations: mocks.list,
}));
vi.mock('../../../src/features/recommendations/api/getBusinessRecommendationPreferences', () => ({
  getBusinessRecommendationPreferences: mocks.preferences,
}));
vi.mock(
  '../../../src/features/configuration/discovery-strategies/api/listDiscoveryStrategies',
  () => ({
    listDiscoveryStrategies: mocks.strategies,
  }),
);
vi.mock('../../../src/features/recommendations/api/listSuppressions', () => ({
  listSuppressions: mocks.suppressions,
}));
vi.mock('../../../src/features/recommendations/api/saveRecommendation', () => ({
  saveRecommendation: mocks.save,
}));
vi.mock('../../../src/features/recommendations/api/getRecommendation', () => ({
  getRecommendation: mocks.get,
}));

function recommendation(): RecommendationView {
  return {
    id: 'rec-lost-save',
    business_id: 'business-1',
    company_id: 'company-1',
    status: 'open',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-02T00:00:00Z',
    current_revision_id: 'revision-1',
    first_presented_at: '2026-11-02T00:00:00Z',
    resolved_at: null,
    resolved_by_user_id: null,
    resolution_reason: null,
    version: 3,
    company: {
      name: 'Committed Northstar',
      domain: 'committed-northstar.example',
      country: 'US',
      business_sector: ['Research'],
      company_scale: '11-50',
      company_status: 'active',
    },
    assessment: {
      id: 'revision-1',
      recommendation_id: 'rec-lost-save',
      business_id: 'business-1',
      company_id: 'company-1',
      revision_number: 1,
      assessed_at: '2026-11-01T00:00:00Z',
      assessed_by_user_id: 'user-1',
      strategy_assessments: [],
      professional_profile_snapshot: {},
      evidence_snapshots: [],
      evidence_observation_ids: [],
      policy_versions: ['test-policy'],
      evaluation_seed: null,
    },
    prospect: null,
    selection_state: {
      first_presented_at: '2026-11-02T00:00:00Z',
      cooldown_until: null,
      paused_until: null,
      paused_indefinitely: false,
      rejected: false,
      has_relationship: false,
      pending_delivery: false,
      uncertain_delivery: false,
    },
    selection_blockers: [],
    current_eligibility: 'not_reassessed',
    read_at: '2026-11-14T00:00:00Z',
    evidence_state: 'current',
    active_blocks: [],
  };
}
function page(items: RecommendationView[], offset = 0): RecommendationPage {
  return { items, offset, limit: 25, has_more: false };
}
beforeEach(() => {
  vi.resetAllMocks();
  mocks.serverCommitted = false;
  mocks.session = { value: { account_id: 'account-1', user_id: 'user-1', csrf_token: 'csrf-1' } };
  const item = recommendation();
  mocks.list.mockImplementation(async ({ search, offset }: { search: string; offset: number }) =>
    mocks.serverCommitted || search ? page([], offset) : page([item], offset),
  );
  mocks.preferences.mockResolvedValue({
    business_id: 'business-1',
    repeat_interval_days: 30,
    updated_at: '2026-11-14T00:00:00Z',
  });
  mocks.strategies.mockResolvedValue({ items: [], has_more: false, offset: 0, limit: 100 });
  mocks.suppressions.mockResolvedValue(page([]));
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'save-request-key') });
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
});

it('keeps a pinned exact-target recovery shelf after a committed Save loses its response and list refetch omits the row', async () => {
  mocks.save
    .mockImplementationOnce(async () => {
      mocks.serverCommitted = true;
      throw new TypeError('response lost after commit');
    })
    .mockResolvedValue({
      recommendation_id: 'rec-lost-save',
      company_id: 'company-1',
      assessment_revision_id: 'revision-1',
      prospect_id: 'prospect-1',
      prospect_stage: 'saved',
      prospect_version: 1,
      origin_id: 'origin-1',
    });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/recommendations', component: RecommendationsPage }],
  });
  await router.push('/recommendations');
  await router.isReady();
  const wrapper = mount(pageHost, {
    global: {
      plugins: [PrimeVue, router, [VueQueryPlugin, { queryClient: client }]],
    },
  });
  await flushPromises();
  expect(wrapper.text()).toContain('Committed Northstar');
  await wrapper.get('button[aria-label="Save as prospect"]').trigger('click');
  await flushPromises();
  expect(mocks.save).toHaveBeenCalledTimes(1);
  expect(wrapper.text()).toContain('Retry the same request');

  await wrapper
    .get('input[aria-label="Search recommendations by company name or domain"]')
    .setValue('another-company.example');
  await flushPromises();
  expect(wrapper.text()).toContain('No recommendations match this view yet.');
  const recovery = wrapper.get('[aria-label="Recommendation drafts awaiting recovery"]');
  expect(recovery.text()).toContain('Committed Northstar');
  expect(recovery.text()).toContain('Retry the same request');
  expect(mocks.save).toHaveBeenCalledTimes(1);

  await recovery.get('button[aria-label="Retry the same request"]').trigger('click');
  await flushPromises();
  expect(mocks.save).toHaveBeenCalledTimes(2);
  expect(mocks.save.mock.calls[1]).toEqual(mocks.save.mock.calls[0]);
  expect(wrapper.text()).toContain('Saved as a prospect');
  wrapper.unmount();
});

it('shows one exact email revision when the list has a newer revision and retains its uncertain Save intent', async () => {
  const old = recommendation();
  if (!old.assessment) throw new Error('Historical fixture needs an assessment');
  const current = {
    ...old,
    current_revision_id: 'revision-new',
    assessment: { ...old.assessment, id: 'revision-new', revision_number: 2 },
  };
  mocks.list.mockResolvedValue(page([current]));
  mocks.get.mockResolvedValue(old);
  mocks.save
    .mockRejectedValueOnce(new TypeError('response lost'))
    .mockResolvedValueOnce({ prospect_id: 'prospect-1' });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/recommendations', component: RecommendationsPage }],
  });
  await router.push(
    '/recommendations?recommendation_id=rec-lost-save&assessment_revision_id=revision-1',
  );
  await router.isReady();
  const wrapper = mount(pageHost, {
    global: {
      plugins: [
        PrimeVue,
        router,
        [
          VueQueryPlugin,
          {
            queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }),
          },
        ],
      ],
    },
  });
  await flushPromises();
  expect(wrapper.findAll('button[aria-label="Save as prospect"]')).toHaveLength(1);
  expect(wrapper.findAll('article.recommendation-card')).toHaveLength(0);
  expect(mocks.get).toHaveBeenCalledWith(old.id, expect.any(AbortSignal), 'revision-1');
  await wrapper.get('button[aria-label="Save as prospect"]').trigger('click');
  await flushPromises();
  await wrapper.get('input[type="search"]').setValue('another-company.example');
  await flushPromises();
  await wrapper.get('button[aria-label="Retry the same request"]').trigger('click');
  await flushPromises();
  expect(mocks.save.mock.calls[0]?.[1].assessment_revision_id).toBe('revision-1');
  expect(mocks.save.mock.calls[1]).toEqual(mocks.save.mock.calls[0]);
  wrapper.unmount();
});
