import { flushPromises, mount } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import PrimeVue from 'primevue/config';
import { beforeEach, expect, it, vi } from 'vitest';
import { reactive } from 'vue';
import { ApiError } from '../../../src/api/apiError';
import LinkedRecommendation from '../../../src/features/recommendations/components/LinkedRecommendation.vue';
import { createRecommendationCommandDraft } from '../../../src/features/recommendations/models/recommendationCommandDraft';
import type { RecommendationView } from '../../../src/features/recommendations/models/prospecting';
import { prospect } from '../prospects/prospectFixture';

const mocks = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), record: vi.fn() }));
vi.mock('../../../src/features/recommendations/api/getRecommendation', () => ({
  getRecommendation: mocks.get,
}));
vi.mock('../../../src/features/recommendations/api/saveRecommendation', () => ({
  saveRecommendation: mocks.save,
}));

vi.mock('../../../src/features/recommendations/api/recordRecommendationFeedback', () => ({
  recordRecommendationFeedback: mocks.record,
}));

function historical(): RecommendationView {
  const saved = prospect();
  return {
    id: 'rec-old',
    business_id: saved.business_id,
    company_id: saved.company_id,
    company: saved.company,
    status: 'open',
    created_at: saved.created_at,
    updated_at: saved.updated_at,
    version: 7,
    current_revision_id: 'new-revision',
    assessment: {
      id: 'old-revision',
      recommendation_id: 'rec-old',
      business_id: saved.business_id,
      company_id: saved.company_id,
      revision_number: 1,
      assessed_at: saved.created_at,
      assessed_by_user_id: 'user-1',
      professional_profile_snapshot: {},
      evidence_snapshots: [],
      evidence_observation_ids: [],
      policy_versions: ['v1'],
      evaluation_seed: null,
      strategy_assessments: [
        {
          strategy_id: 'strategy-1',
          offering_id: 'offer-1',
          ideal_client_profile_id: 'icp-1',
          strategy_snapshot: { name: 'Research' },
          offering_snapshot: {},
          ideal_client_profile_snapshot: {},
          assessment_snapshot: { rationale: 'Recent hiring suggests a research workflow review.' },
        },
      ],
    },
    first_presented_at: '2026-11-01T10:00:00Z',
    assessment_presented_at: '2026-11-01T10:00:00Z',
    resolved_at: null,
    resolved_by_user_id: null,
    resolution_reason: null,
    prospect: null,
    selection_blockers: [],
    active_blocks: [],
    current_eligibility: 'not_reassessed',
    evidence_state: 'changed',
    read_at: saved.updated_at,
    selection_state: {
      first_presented_at: '2026-11-01T10:00:00Z',
      cooldown_until: null,
      paused_until: null,
      paused_indefinitely: false,
      rejected: false,
      has_relationship: false,
      pending_delivery: false,
      uncertain_delivery: false,
    },
  };
}

beforeEach(() => {
  vi.resetAllMocks();
});

async function render() {
  const item = historical();
  mocks.get.mockResolvedValue(item);
  const wrapper = mount(LinkedRecommendation, {
    props: {
      recommendationId: item.id,
      assessmentRevisionId: 'old-revision',
      identity: 'owner:session',
      draftState: reactive(createRecommendationCommandDraft(item.id)),
      preferences: {
        business_id: item.business_id,
        repeat_interval_days: 30,
        updated_at: item.updated_at,
      },
      preferencesLoading: false,
      preferencesFailed: false,
      refreshPreferences: vi.fn(),
    },
    global: {
      stubs: { Select: true },
      plugins: [
        PrimeVue,
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
  return { wrapper, item };
}

it('renders the email revision and attributes Save to it even when a newer revision exists', async () => {
  mocks.save.mockResolvedValue({ prospect_id: 'saved-prospect' });
  const { wrapper, item } = await render();
  expect(mocks.get).toHaveBeenCalledWith(item.id, expect.any(AbortSignal), 'old-revision');
  expect(wrapper.text()).toContain('Recommendation from your email');
  expect(wrapper.text()).toContain('Company signals');
  expect(wrapper.text()).not.toContain('Recent hiring suggests a research workflow review.');
  expect(wrapper.get('details').attributes('open')).toBeUndefined();
  expect(mocks.save).not.toHaveBeenCalled();
  await wrapper.get('button[aria-label="Save as prospect"]').trigger('click');
  await flushPromises();
  expect(mocks.save).toHaveBeenCalledWith(
    item.id,
    expect.objectContaining({ assessment_revision_id: 'old-revision' }),
  );
  wrapper.unmount();
});

it('does not substitute the current assessment when the exact linked revision is unavailable', async () => {
  const { wrapper, item } = await render();
  mocks.get.mockResolvedValue({ ...item, assessment: { ...item.assessment, id: 'new-revision' } });
  await wrapper.setProps({ assessmentRevisionId: 'missing-old-revision' });
  await flushPromises();
  expect(wrapper.text()).toContain('The linked assessment could not be loaded.');
  expect(wrapper.find('button[aria-label="Save as prospect"]').exists()).toBe(false);
  expect(mocks.save).not.toHaveBeenCalled();
  wrapper.unmount();
});

it('keeps a rejected report editable after cancelling a decision while the report is pending', async () => {
  let rejectReport!: (error: unknown) => void;
  mocks.record.mockReturnValue(
    new Promise((_, reject) => {
      rejectReport = reject;
    }),
  );
  const { wrapper } = await render();
  const draft = wrapper.props('draftState');
  expect(wrapper.find('.quality-feedback').exists()).toBe(false);
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
    const { wrapper } = await render();
    const draft = wrapper.props('draftState');
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
    const { wrapper } = await render();
    const draft = wrapper.props('draftState');
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
