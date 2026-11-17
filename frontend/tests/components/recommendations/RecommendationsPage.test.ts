import { flushPromises, mount } from '@vue/test-utils';
import { reactive, ref } from 'vue';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import PrimeVue from 'primevue/config';
import { ApiError } from '../../../src/api/apiError';
import {
  createRecommendationCommandDraft,
  type RecommendationCommandDraft,
} from '../../../src/features/recommendations/models/recommendationCommandDraft';
import { beforeEach, expect, it, vi } from 'vitest';
import RecommendationsPage from '../../../src/features/recommendations/pages/RecommendationsPage.vue';
import type { RecommendationView } from '../../../src/features/recommendations/models/prospecting';

const mocks = vi.hoisted(() => ({ workspace: null as unknown, record: vi.fn(), save: vi.fn() }));
vi.mock('../../../src/features/recommendations/composables/useRecommendationWorkspace', () => ({
  useRecommendationWorkspace: () => mocks.workspace,
}));
vi.mock('../../../src/features/recommendations/api/saveRecommendation', () => ({
  saveRecommendation: mocks.save,
}));
vi.mock('../../../src/features/recommendations/api/recordRecommendationFeedback', () => ({
  recordRecommendationFeedback: mocks.record,
}));
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
    assessment_presented_at: null,
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
function setup(items = [recommendation()], realCommands = false) {
  const commandDrafts = new Map<string, RecommendationCommandDraft>();
  const list = {
    data: ref({ items, offset: 0, limit: 25, has_more: false }),
    isPending: ref(false),
    isError: ref(false),
    isFetching: ref(false),
    refetch: vi.fn(),
  };
  const workspace = {
    identity: ref('account-1:user-1:csrf'),
    strategyId: ref('strategy-1'),
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
        draft = reactive(createRecommendationCommandDraft(id));
        commandDrafts.set(id, draft);
      }
      return draft;
    },
  };
  mocks.workspace = workspace;
  return mount(RecommendationsPage, {
    global: {
      plugins: [
        PrimeVue,
        [
          VueQueryPlugin,
          { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
        ],
      ],
      stubs: {
        RecommendationCommandActions: realCommands
          ? false
          : {
              props: ['draftState'],
              template:
                '<div data-test="decision-actions" :data-reason="draftState?.reason" :data-status="draftState?.status" />',
            },
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
  vi.resetAllMocks();
  mocks.workspace = null;
});

it('keeps company signals collapsed before decision actions without metadata boilerplate', () => {
  const wrapper = setup();
  const text = wrapper.text();
  const cardHtml = wrapper.find('article.recommendation-card').html();
  expect(text).toContain('Search your recommendations by company name or domain.');
  expect(text).not.toContain('filters before pagination');
  expect(text).not.toContain('Recommendation version');
  expect(text).not.toContain('A cited research group is expanding its data team.');
  expect(text).toContain('We are hiring two data analysts.');
  expect(wrapper.get('a[href="https://northstar.example/jobs"]').text()).toContain('Open source');
  expect(text).toContain('Source date:');
  expect(text).toContain('Company info');
  expect(wrapper.find('.quality-feedback').exists()).toBe(false);
  expect(wrapper.get('details').attributes('open')).toBeUndefined();
  expect(text).not.toContain('differs from this assessment');
  expect(cardHtml.indexOf('Company signals')).toBeLessThan(
    cardHtml.indexOf('data-test="decision-actions"'),
  );
  expect(wrapper.find('button[aria-label="Close recommendation"]').exists()).toBe(false);
});

it('prompts for a strategy without rendering cached list rows when none is selected', async () => {
  const wrapper = setup();
  const workspace = mocks.workspace as { strategyId: { value: string } };
  workspace.strategyId.value = '';
  await wrapper.vm.$nextTick();
  expect(wrapper.text()).toContain('Choose a discovery strategy to view its recommendations.');
  expect(wrapper.find('article.recommendation-card').exists()).toBe(false);
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
  expect(shelf.text()).toContain('Company signals');
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

it('shows unsubmitted recommendation feedback only while a negative decision is open', async () => {
  const wrapper = setup();
  const workspace = mocks.workspace as {
    commandDraftFor: (id: string) => { laterConfirmationOpen: boolean };
  };
  expect(wrapper.find('.quality-feedback').exists()).toBe(false);
  workspace.commandDraftFor('recommendation-1').laterConfirmationOpen = true;
  await wrapper.vm.$forceUpdate();
  expect(wrapper.find('.quality-feedback').exists()).toBe(true);
  workspace.commandDraftFor('recommendation-1').laterConfirmationOpen = false;
  await wrapper.vm.$forceUpdate();
  expect(wrapper.find('.quality-feedback').exists()).toBe(false);
});

it('keeps a rejected report editable after cancelling a decision while the report is pending', async () => {
  let rejectReport!: (error: unknown) => void;
  mocks.record.mockReturnValue(
    new Promise((_, reject) => {
      rejectReport = reject;
    }),
  );
  const wrapper = setup([recommendation()], true);
  const workspace = mocks.workspace as {
    commandDraftFor: (id: string) => RecommendationCommandDraft;
  };
  const draft = workspace.commandDraftFor('recommendation-1');
  await wrapper.get('button[aria-label="Not relevant"]').trigger('click');
  const report = wrapper.get('.quality-feedback');
  await report.get('select').setValue('not_useful');
  await report.get('input[value="evidence_wrong"]').setValue(true);
  await report.get('textarea').setValue('The source has changed.');
  await report.get('label:last-of-type textarea').setValue('Please review the original evidence.');
  await report.get('form').trigger('submit');
  expect(draft.feedback.status).toBe('pending');
  const cancel = wrapper.findAll('button').find((button) => button.text() === 'Cancel');
  if (!cancel) throw new Error('Decision cancellation was not rendered');
  await cancel.trigger('click');
  expect(wrapper.find('.quality-feedback').exists()).toBe(true);
  rejectReport(new ApiError(422, 'validation_error', 'Invalid report'));
  await flushPromises();

  expect(wrapper.find('.quality-feedback').exists()).toBe(true);
  expect(wrapper.get('.quality-feedback [role="alert"]').text()).toContain(
    'Feedback was not accepted',
  );
  expect(wrapper.get<HTMLSelectElement>('.quality-feedback select').element.value).toBe(
    'not_useful',
  );
  expect(wrapper.get<HTMLInputElement>('input[value="evidence_wrong"]').element.checked).toBe(true);
  expect(wrapper.get<HTMLTextAreaElement>('.quality-feedback textarea').element.value).toBe(
    'The source has changed.',
  );
  expect(
    wrapper.get<HTMLTextAreaElement>('.quality-feedback label:last-of-type textarea').element.value,
  ).toBe('Please review the original evidence.');
  expect(wrapper.get('.quality-feedback select').attributes('disabled')).toBeUndefined();
  expect(draft.feedback.intent).toBeNull();
  await wrapper.get('.quality-feedback textarea').setValue('Corrected source details.');
  expect(draft.feedback.correction).toBe('Corrected source details.');
  wrapper.unmount();
});

it.each(['idle', 'error'] as const)(
  'closes and discards an %s report after saving as a prospect',
  async (status) => {
    mocks.save.mockResolvedValue({ prospect_id: 'saved-prospect' });
    const wrapper = setup([recommendation()], true);
    const draft = (
      mocks.workspace as { commandDraftFor: (id: string) => RecommendationCommandDraft }
    ).commandDraftFor('recommendation-1');
    await wrapper.get('button[aria-label="Not relevant"]').trigger('click');
    await wrapper.get('.quality-feedback select').setValue('not_useful');
    await wrapper.get('.quality-feedback textarea').setValue('Temporary correction.');
    if (status === 'error') {
      mocks.record.mockRejectedValue(new ApiError(422, 'validation_error', 'Invalid report'));
      await wrapper.get('.quality-feedback form').trigger('submit');
      await flushPromises();
      expect(draft.feedback.status).toBe('error');
    }
    await wrapper.get('button[aria-label="Save as prospect"]').trigger('click');
    await flushPromises();
    expect(mocks.save).toHaveBeenCalledOnce();
    expect(wrapper.find('.quality-feedback').exists()).toBe(false);
    expect(draft.feedback).toEqual(
      createRecommendationCommandDraft(draft.recommendationId).feedback,
    );
    wrapper.unmount();
  },
);

it.each(['pending', 'uncertain'] as const)(
  'preserves a submitted %s report after saving as a prospect',
  async (status) => {
    mocks.save.mockResolvedValue({ prospect_id: 'saved-prospect' });
    if (status === 'pending') mocks.record.mockReturnValue(new Promise(() => {}));
    else mocks.record.mockRejectedValue(new TypeError('Network interrupted'));
    const wrapper = setup([recommendation()], true);
    const draft = (
      mocks.workspace as { commandDraftFor: (id: string) => RecommendationCommandDraft }
    ).commandDraftFor('recommendation-1');
    await wrapper.get('button[aria-label="Not relevant"]').trigger('click');
    await wrapper.get('.quality-feedback select').setValue('not_useful');
    await wrapper.get('.quality-feedback textarea').setValue('Submitted correction.');
    await wrapper.get('.quality-feedback form').trigger('submit');
    await flushPromises();
    const intent = draft.feedback.intent;
    expect(intent).not.toBeNull();
    expect(draft.feedback.status).toBe(status);
    await wrapper.get('button[aria-label="Save as prospect"]').trigger('click');
    await flushPromises();
    expect(mocks.save).toHaveBeenCalledOnce();
    expect(wrapper.find('.quality-feedback').exists()).toBe(true);
    expect(draft.feedback.intent).toBe(intent);
    expect(draft.feedback.status).toBe(status);
    expect(draft.feedback.correction).toBe('Submitted correction.');
    wrapper.unmount();
  },
);
