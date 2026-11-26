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
  prepare: vi.fn(),
  confirm: vi.fn(),
  generate: vi.fn(),
  visible: null as ((entries: { isIntersecting: boolean }[]) => void) | null,
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
vi.mock('../../../src/features/recommendations/api/prepareRecommendationOffer', () => ({
  prepareRecommendationOffer: mocks.prepare,
}));
vi.mock('../../../src/features/recommendations/api/confirmRecommendationOffer', () => ({
  confirmRecommendationOffer: mocks.confirm,
}));
vi.mock('../../../src/features/recommendations/api/generateRecommendations', () => ({
  generateRecommendations: mocks.generate,
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
    assessment_presented_at: '2026-11-02T00:00:00Z',
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
  mocks.strategies.mockResolvedValue({
    items: [
      {
        id: 'strategy-1',
        name: 'Research teams',
        service_offering_id: 'offering-1',
        ideal_client_profile_id: 'icp-1',
      },
    ],
    has_more: false,
    offset: 0,
    limit: 100,
  });
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
    assessment_presented_at: null,
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

it.each(['fresh', 'newly selected repeat'] as const)(
  'coordinates an unrelated %s offer while preserving the exact historical email assessment',
  async (kind) => {
    const linked = recommendation();
    if (!linked.assessment) throw new Error('Historical fixture needs an assessment');
    const unrelated: RecommendationView = {
      ...linked,
      id: `rec-unrelated-${kind}`,
      company_id: 'company-2',
      company: { ...linked.company, name: 'Unrelated Company', domain: 'unrelated.example' },
      current_revision_id: 'revision-unrelated',
      first_presented_at: kind === 'fresh' ? null : '2026-01-01T00:00:00Z',
      assessment_presented_at: null,
      selection_state: {
        ...linked.selection_state,
        first_presented_at: kind === 'fresh' ? null : '2026-01-01T00:00:00Z',
      },
      assessment: {
        ...linked.assessment,
        id: 'revision-unrelated',
        recommendation_id: `rec-unrelated-${kind}`,
        company_id: 'company-2',
      },
    };
    const linkedCurrent: RecommendationView = {
      ...linked,
      current_revision_id: 'revision-linked-new',
      assessment_presented_at: null,
      assessment: { ...linked.assessment, id: 'revision-linked-new', revision_number: 2 },
    };
    mocks.list.mockResolvedValue(page([linkedCurrent, unrelated]));
    mocks.get.mockResolvedValue(linked);
    mocks.strategies.mockResolvedValue({
      items: [
        {
          id: 'strategy-1',
          name: 'Research teams',
          service_offering_id: 'offering-1',
          ideal_client_profile_id: 'icp-1',
        },
      ],
      has_more: false,
      offset: 0,
      limit: 100,
    });
    mocks.generate.mockResolvedValue({
      references: [{ recommendation_id: unrelated.id, revision_id: 'revision-unrelated' }],
    });
    mocks.prepare.mockResolvedValue({
      recommendation_id: unrelated.id,
      assessment_revision_id: 'revision-unrelated',
      offer_cycle_id: 'cycle-unrelated',
      status: 'preparing',
      claim_token: 'claim-unrelated',
    });
    mocks.confirm.mockResolvedValue({ presented_at: '2026-11-14T12:00:00Z' });
    mocks.save.mockResolvedValue({ prospect_id: 'prospect-1' });
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(callback: typeof mocks.visible) {
          mocks.visible = callback;
        }
        observe() {}
        disconnect() {}
      },
    );
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 200,
      height: 100,
      top: 0,
      bottom: 100,
      left: 0,
      right: 200,
      x: 0,
      y: 0,
      toJSON() {},
    });
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/recommendations', component: RecommendationsPage }],
    });
    await router.push({
      path: '/recommendations',
      query: { recommendation_id: linked.id, assessment_revision_id: linked.assessment.id },
    });
    await router.isReady();
    const wrapper = mount(pageHost, {
      attachTo: document.body,
      global: {
        plugins: [
          PrimeVue,
          router,
          [
            VueQueryPlugin,
            { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
          ],
        ],
      },
    });
    await flushPromises();
    const email = wrapper.get('[aria-label="Recommendation from your email"]');
    expect(
      email.get('[data-assessment-revision-id]').attributes('data-assessment-revision-id'),
    ).toBe('revision-1');
    expect(wrapper.findAll('article.recommendation-card')).toHaveLength(1);
    if (kind === 'newly selected repeat') {
      const generate = wrapper
        .findAll('button')
        .find((button) => button.text().includes('Generate recommendations'));
      if (!generate) throw new Error('Generation action is unavailable');
      await generate.trigger('click');
      await flushPromises();
      expect(mocks.generate).toHaveBeenCalledWith('strategy-1', 10);
    }
    const card = wrapper.get('article.recommendation-card');
    expect(card.text()).toContain('Preparing Unrelated Company');
    expect(card.find('button[aria-label="Save as prospect"]').exists()).toBe(false);
    expect(mocks.prepare).not.toHaveBeenCalled();
    expect(mocks.confirm).not.toHaveBeenCalled();

    mocks.visible?.([{ isIntersecting: true }]);
    await flushPromises();
    expect(mocks.prepare).toHaveBeenCalledExactlyOnceWith(unrelated.id, {
      assessment_revision_id: 'revision-unrelated',
      request_key: 'save-request-key',
    });
    expect(mocks.confirm).not.toHaveBeenCalled();
    mocks.visible?.([{ isIntersecting: true }]);
    await flushPromises();
    expect(mocks.confirm).toHaveBeenCalledExactlyOnceWith('cycle-unrelated', {
      claim_token: 'claim-unrelated',
    });
    await card.get('button[aria-label="Save as prospect"]').trigger('click');
    await flushPromises();
    expect(mocks.save).toHaveBeenCalledWith(unrelated.id, {
      assessment_revision_id: 'revision-unrelated',
      request_key: 'save-request-key',
    });
    await email.get('button[aria-label="Save as prospect"]').trigger('click');
    await flushPromises();
    expect(mocks.save).toHaveBeenLastCalledWith(linked.id, {
      assessment_revision_id: 'revision-1',
      request_key: 'save-request-key',
    });
    expect(mocks.prepare).toHaveBeenCalledTimes(1);
    expect(mocks.confirm).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  },
);
