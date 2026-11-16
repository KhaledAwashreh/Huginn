import { mount } from '@vue/test-utils';
import { ref } from 'vue';
import { beforeEach, expect, it, vi } from 'vitest';
import RecommendationsPage from '../../../src/features/recommendations/pages/RecommendationsPage.vue';
import type { RecommendationView } from '../../../src/features/recommendations/models/prospecting';

const mocks = vi.hoisted(() => ({ workspace: null as unknown }));
vi.mock('../../../src/features/recommendations/composables/useRecommendationWorkspace', () => ({
  useRecommendationWorkspace: () => mocks.workspace,
}));
vi.mock(
  '../../../src/features/recommendations/components/RecommendationCommandActions.vue',
  () => ({
    default: {
      props: ['draftState'],
      template:
        '<div data-test="decision-actions" :data-reason="draftState?.reason" :data-status="draftState?.status" />',
    },
  }),
);
vi.mock(
  '../../../src/features/recommendations/components/RecommendationQualityFeedback.vue',
  () => ({
    default: { template: '<div data-test="quality-feedback" />' },
  }),
);
function recommendation(status: RecommendationView['status'] = 'open'): RecommendationView {
  return {
    id: 'recommendation-1',
    business_id: 'business-1',
    company_id: 'company-1',
    status,
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    current_revision_id: 'revision-1',
    first_presented_at: null,
    resolved_at: status === 'open' ? null : '2026-11-02T00:00:00Z',
    resolved_by_user_id: status === 'open' ? null : 'user-1',
    resolution_reason: status === 'rejected' ? 'Wrong buyer' : null,
    version: 3,
    company: {
      name: 'Northstar Labs',
      domain: 'northstar.example',
      business_sector: ['Research'],
      country: 'US',
      company_scale: '11-50',
      company_status: 'active',
    },
    assessment: {
      id: 'revision-1',
      recommendation_id: 'recommendation-1',
      business_id: 'business-1',
      company_id: 'company-1',
      revision_number: 2,
      assessed_at: '2026-11-01T00:00:00Z',
      assessed_by_user_id: 'user-1',
      strategy_assessments: [
        {
          strategy_id: 'strategy-1',
          offering_id: 'offering-1',
          ideal_client_profile_id: 'icp-1',
          strategy_snapshot: { name: 'Product research' },
          offering_snapshot: { name: 'Research service' },
          ideal_client_profile_snapshot: { name: 'Research teams' },
          assessment_snapshot: {
            rationale: 'A cited research group is expanding its data team.',
            unknowns: ['The purchase owner is unknown.'],
            evidence: [
              {
                observation_id: 'observation-1',
                quote: 'We are hiring two data analysts.',
              },
            ],
            company_facts: { country: 'US', company_scale: '11-50' },
          },
        },
      ],
      professional_profile_snapshot: { headline: 'Independent researcher' },
      evidence_snapshots: [
        {
          observation_id: 'observation-1',
          source: 'yc',
          quote: 'We are hiring two data analysts.',
          source_url: 'https://northstar.example/jobs',
          occurred_at: '2026-10-31T00:00:00Z',
          observed_at: '2026-11-01T00:00:00Z',
        },
      ],
      evidence_observation_ids: ['observation-1'],
      policy_versions: ['fit-v1'],
      evaluation_seed: 'seed-1',
    },
    prospect: null,
    selection_state: {
      first_presented_at: null,
      cooldown_until: null,
      paused_until: null,
      paused_indefinitely: false,
      rejected: false,
      has_relationship: false,
      pending_delivery: false,
      uncertain_delivery: false,
    },
    selection_blockers: [],
    current_eligibility: status === 'open' ? 'not_reassessed' : 'historical',
    read_at: '2026-11-14T00:00:00Z',
    evidence_state: 'changed',
    active_blocks: [],
  };
}
function setup(items = [recommendation()]) {
  const commandDrafts = new Map<
    string,
    {
      reason: string;
      pauseChoice: string;
      laterConfirmationOpen: boolean;
      recommendationId: string;
      snapshot: RecommendationView | null;
      status: string;
      error: string;
      intent: unknown;
      feedback: { open: boolean };
    }
  >();
  const list = {
    data: ref({ items, offset: 0, limit: 25, has_more: false }),
    isPending: ref(false),
    isError: ref(false),
    isFetching: ref(false),
    refetch: vi.fn(),
  };
  const workspace = {
    identity: ref('account-1:user-1:csrf'),
    search: ref(''),
    status: ref('open'),
    offset: ref(0),
    recommendations: list,
    commandRecoveries: ref([]),
    preferences: {
      data: ref({ repeat_interval_days: 30, updated_at: '2026-11-14T00:00:00Z' }),
      isPending: ref(false),
      isError: ref(false),
      refetch: vi.fn(),
    },
    suppressions: {
      data: ref(undefined),
      isPending: ref(false),
      isError: ref(false),
      isFetching: ref(false),
    },
    suppressionsVisible: ref(false),
    suppressionSearch: ref(''),
    suppressionOffset: ref(0),
    strategies: {
      data: ref([{ id: 'strategy-1', name: 'Product research' }]),
      isPending: ref(false),
      isError: ref(false),
      refetch: vi.fn(),
    },
    generating: ref(false),
    generationError: ref(''),
    generationResult: ref(null),
    setOffset: vi.fn(),
    setSuppressionOffset: vi.fn(),
    refresh: vi.fn(),
    refreshPreferences: vi.fn(async () => ({
      repeat_interval_days: 30,
      updated_at: '2026-11-14T00:00:00Z',
    })),
    generate: vi.fn(),
    commandDraftFor: (id: string) => {
      let draft = commandDrafts.get(id);
      if (!draft) {
        draft = {
          recommendationId: id,
          snapshot: null,
          reason: '',
          pauseChoice: 'x1',
          laterConfirmationOpen: false,
          status: 'idle',
          error: '',
          intent: null,
          feedback: { open: false },
        };
        commandDrafts.set(id, draft);
      }
      return draft;
    },
  };
  mocks.workspace = workspace;
  return mount(RecommendationsPage, {
    global: {
      stubs: {
        PageHeader: {
          template: '<header><h1>{{ title }}</h1></header>',
          props: ['title', 'description'],
        },
        ErrorState: { template: '<div><slot /></div>', props: ['message'] },
        EmptyState: { template: '<p>{{ message }}</p>', props: ['message'] },
        LoadingState: { template: '<p>{{ message }}</p>', props: ['message'] },
        SuppressionManagement: true,
        Select: { template: '<select />', props: ['options', 'modelValue'] },
        RouterLink: { template: '<a><slot /></a>', props: ['to'] },
      },
    },
  });
}
beforeEach(() => {
  mocks.workspace = null;
});

it('shows revision rationale and cited assessment-time evidence before decision actions', () => {
  const wrapper = setup();
  const text = wrapper.text();
  const cardHtml = wrapper.find('article.recommendation-card').html();
  expect(text).toContain('Search covers the full Business dataset');
  expect(text).toContain('A cited research group is expanding its data team.');
  expect(text).toContain('We are hiring two data analysts.');
  expect(wrapper.get('a[href="https://northstar.example/jobs"]').text()).toContain('Open source');
  expect(text).toContain('Source date:');
  expect(text).toContain('Current company context');
  expect(text).toContain('differs from this assessment');
  expect(cardHtml.indexOf('A cited research group')).toBeLessThan(
    cardHtml.indexOf('data-test="decision-actions"'),
  );
  expect(wrapper.find('button[aria-label="Close recommendation"]').exists()).toBe(false);
});

it('keeps resolved recommendations readable and removes all decision actions', () => {
  const wrapper = setup([recommendation('rejected')]);
  expect(wrapper.text()).toContain('This recommendation is resolved.');
  expect(wrapper.text()).toContain('Not relevant');
  expect(wrapper.find('[data-test="decision-actions"]').exists()).toBe(false);
});

it('restores a pending command draft after the recommendation row is removed and remounted', async () => {
  const wrapper = setup([recommendation()]);
  const workspace = mocks.workspace as {
    recommendations: { data: { value: { items: RecommendationView[] } } };
    commandDraftFor: (id: string) => {
      reason: string;
      status: string;
      intent: unknown;
    };
  };
  const draft = workspace.commandDraftFor('recommendation-1');
  draft.reason = 'The buyer role remains unverified.';
  draft.status = 'uncertain';
  draft.intent = { request: { request_key: 'pending-save-key' } };
  workspace.recommendations.data.value.items = [];
  await wrapper.vm.$nextTick();
  expect(wrapper.find('[data-test="decision-actions"]').exists()).toBe(false);

  workspace.recommendations.data.value.items = [recommendation()];
  await wrapper.vm.$nextTick();
  expect(wrapper.get('[data-test="decision-actions"]').attributes('data-reason')).toBe(
    'The buyer role remains unverified.',
  );
  expect(wrapper.get('[data-test="decision-actions"]').attributes('data-status')).toBe('uncertain');
});

it('shows a pinned recovery copy when a command target is outside the current server result page', async () => {
  const wrapper = setup([]);
  const workspace = mocks.workspace as {
    commandRecoveries: { value: unknown[] };
    commandDraftFor: (id: string) => {
      recommendationId: string;
      snapshot: RecommendationView | null;
      reason: string;
      status: string;
      intent: unknown;
      decisionDraft: boolean;
      feedbackDraft: boolean;
    };
  };
  const snapshot = recommendation();
  const draft = workspace.commandDraftFor(snapshot.id);
  draft.snapshot = snapshot;
  draft.reason = 'The request receipt is uncertain.';
  draft.status = 'uncertain';
  draft.intent = { recommendationId: snapshot.id, request: { request_key: 'retry-key' } };
  workspace.commandRecoveries.value = [
    {
      recommendationId: snapshot.id,
      snapshot,
      draft,
      decisionDraft: true,
      feedbackDraft: false,
    },
  ];
  await wrapper.vm.$nextTick();

  const shelf = wrapper.get('[aria-label="Recommendation drafts awaiting recovery"]');
  expect(shelf.text()).toContain('Northstar Labs');
  expect(shelf.text()).toContain('A cited research group is expanding its data team.');
  expect(shelf.get('[data-test="decision-actions"]').attributes('data-status')).toBe('uncertain');
});

it('uses the server search input without locally filtering loaded rows', async () => {
  const wrapper = setup([recommendation()]);
  await wrapper
    .get('input[aria-label="Search recommendations by company name or domain"]')
    .setValue('not-on-this-page.example');
  expect((mocks.workspace as { search: { value: string } }).search.value).toBe(
    'not-on-this-page.example',
  );
  expect(wrapper.find('ol.recommendation-list').exists()).toBe(true);
});
