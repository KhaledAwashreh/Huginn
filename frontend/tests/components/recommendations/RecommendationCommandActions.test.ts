import { flushPromises, mount } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { beforeEach, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import { ApiError } from '../../../src/api/apiError';
import RecommendationCommandActions from '../../../src/features/recommendations/components/RecommendationCommandActions.vue';
import type {
  RecommendationView,
  RecommendationPreferences,
} from '../../../src/features/recommendations/models/prospecting';

const mocks = vi.hoisted(() => ({
  save: vi.fn(),
  later: vi.fn(),
  refreshPreferences: vi.fn(),
}));
vi.mock('../../../src/features/recommendations/api/saveRecommendation', () => ({
  saveRecommendation: mocks.save,
}));
vi.mock('../../../src/features/recommendations/api/markRecommendationNotRelevant', () => ({
  markRecommendationNotRelevant: vi.fn(),
}));
vi.mock('../../../src/features/recommendations/api/laterRecommendation', () => ({
  laterRecommendation: mocks.later,
}));
function model(): RecommendationView {
  return {
    id: 'rec-1',
    business_id: 'business-1',
    company_id: 'company-1',
    status: 'open',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-02T00:00:00Z',
    current_revision_id: 'revision-1',
    first_presented_at: null,
    assessment_presented_at: null,
    resolved_at: null,
    resolved_by_user_id: null,
    resolution_reason: null,
    version: 7,
    company: {
      name: 'Northstar',
      domain: 'northstar.example',
      business_sector: null,
      country: null,
      company_scale: null,
      company_status: null,
    },
    assessment: { id: 'revision-1' } as RecommendationView['assessment'],
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
    current_eligibility: 'not_reassessed',
    read_at: '2026-11-14T00:00:00Z',
    evidence_state: 'current',
    active_blocks: [],
  } as RecommendationView;
}
const preferences: RecommendationPreferences = {
  business_id: 'business-1',
  repeat_interval_days: 30,
  updated_at: '2026-11-14T10:00:00Z',
};
function setup(recommendation = model()) {
  return mount(RecommendationCommandActions, {
    props: {
      recommendation,
      preferences,
      preferencesLoading: false,
      preferencesFailed: false,
      identity: 'account-1:user-1:csrf-1',
      refreshPreferences: mocks.refreshPreferences,
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
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(text));
  if (!button) throw new Error(`Button containing "${text}" was not found`);
  return button;
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'same-request-key') });
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

it('opens a mute panel instead of permanently rejecting the recommendation', async () => {
  const wrapper = setup();
  await buttonWithText(wrapper, 'Not relevant').trigger('click');
  expect(wrapper.text()).toContain('How long should this company be muted?');
  expect(wrapper.text()).toContain('Until I turn it back on');
  expect(mocks.later).not.toHaveBeenCalled();
});

it('mutes for the chosen number of days with an optional reason and replaces the active pause', async () => {
  mocks.later.mockResolvedValue({
    recommendation_id: 'rec-1',
    recommendation_version: 8,
    pause_choice: 'd90',
    repeat_interval_days: 30,
    selected_at: '2026-11-14T10:00:00Z',
    expires_at: '2027-02-12T10:00:00Z',
    suppression_block_id: 'new-pause',
    replaced_pause_id: 'old-pause',
    remaining_blockers: [],
  });
  const recommendation = model();
  recommendation.active_blocks = [
    {
      id: 'old-pause',
      business_id: 'business-1',
      company_id: 'company-1',
      kind: 'pause',
      created_at: '2026-11-01T00:00:00Z',
      effective_at: '2026-11-01T00:00:00Z',
      created_by_user_id: 'user-1',
      expires_at: '2026-12-01T00:00:00Z',
      cleared_at: null,
      cleared_by_user_id: null,
      reason: null,
      version: 3,
    },
  ];
  const wrapper = setup(recommendation);
  await buttonWithText(wrapper, 'Not relevant').trigger('click');
  await wrapper.get('textarea').setValue('Wrong buyer');
  await wrapper.get('input[type="number"]').setValue(90);
  await buttonWithText(wrapper, 'Confirm').trigger('click');
  await flushPromises();

  expect(mocks.later).toHaveBeenCalledWith('rec-1', {
    assessment_revision_id: 'revision-1',
    expected_pause_id: 'old-pause',
    expected_pause_version: 3,
    expected_preference_updated_at: preferences.updated_at,
    expected_recommendation_version: 7,
    expected_repeat_interval_days: 30,
    pause_choice: 'd90',
    reason: 'Wrong buyer',
    request_key: 'same-request-key',
  });
  expect(wrapper.emitted('completed')?.[0]?.[0]).toMatchObject({
    kind: 'later',
    message: 'Muted until 2027-02-12 10:00:00.000 UTC.',
  });
});

it('mutes until the user turns it back on', async () => {
  mocks.later.mockResolvedValue({
    recommendation_id: 'rec-1',
    recommendation_version: 8,
    pause_choice: 'indefinite',
    repeat_interval_days: 30,
    selected_at: '2026-11-14T10:00:00Z',
    expires_at: null,
    suppression_block_id: 'new-pause',
    replaced_pause_id: null,
    remaining_blockers: [],
  });
  const wrapper = setup();
  await buttonWithText(wrapper, 'Not relevant').trigger('click');
  await wrapper.findAll('input[type="radio"]')[1]?.setValue(true);
  await buttonWithText(wrapper, 'Confirm').trigger('click');
  await flushPromises();

  expect(mocks.later).toHaveBeenCalledWith(
    'rec-1',
    expect.objectContaining({ pause_choice: 'indefinite', reason: null }),
  );
  expect(wrapper.emitted('completed')?.[0]?.[0]).toMatchObject({
    kind: 'later',
    message: 'Muted until you turn it back on.',
  });
});

it('retries an uncertain mute against its original recommendation target after a row prop changes', async () => {
  mocks.later.mockRejectedValueOnce(new TypeError('network interrupted')).mockResolvedValue({
    recommendation_id: 'rec-1',
    recommendation_version: 8,
    pause_choice: 'd30',
    repeat_interval_days: 30,
    selected_at: '2026-11-14T11:00:00Z',
    expires_at: '2026-12-14T10:00:00Z',
    suppression_block_id: 'block-1',
    replaced_pause_id: null,
    remaining_blockers: [],
  });
  const wrapper = setup();
  await buttonWithText(wrapper, 'Not relevant').trigger('click');
  await wrapper.get('textarea').setValue('Wrong buyer');
  await buttonWithText(wrapper, 'Confirm').trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('Retry the same update safely.');
  const firstRequest = mocks.later.mock.calls[0];

  const changedRecommendation = model();
  changedRecommendation.id = 'rec-2';
  const changedAssessment = changedRecommendation.assessment;
  if (!changedAssessment) throw new Error('Test recommendation needs an assessment');
  changedAssessment.id = 'revision-2';
  await wrapper.setProps({ recommendation: changedRecommendation });
  await buttonWithText(wrapper, 'Retry the same request').trigger('click');
  await flushPromises();

  expect(mocks.later).toHaveBeenCalledTimes(2);
  expect(mocks.later.mock.calls[1]).toEqual(firstRequest);
  expect(mocks.later.mock.calls[1]?.[0]).toBe('rec-1');
});

it('retains an editable stale mute draft until the user refreshes server state', async () => {
  mocks.later.mockRejectedValue(new ApiError(409, 'conflict', 'stale version'));
  const wrapper = setup();
  await buttonWithText(wrapper, 'Not relevant').trigger('click');
  const reason = wrapper.get('textarea');
  await reason.setValue('Wrong buyer');
  await buttonWithText(wrapper, 'Confirm').trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('Refresh current state');
  expect(reason.element.value).toBe('Wrong buyer');
  expect((reason.element as HTMLTextAreaElement).disabled).toBe(true);
  await buttonWithText(wrapper, 'Refresh current state').trigger('click');
  await flushPromises();
  expect(reason.element.value).toBe('Wrong buyer');
  expect((reason.element as HTMLTextAreaElement).disabled).toBe(false);
});

it('saves the exact shown revision and emits the prospect transition result', async () => {
  mocks.save.mockResolvedValue({
    recommendation_id: 'rec-1',
    company_id: 'company-1',
    assessment_revision_id: 'revision-1',
    prospect_id: 'prospect-1',
    prospect_stage: 'saved',
    prospect_version: 1,
    origin_id: 'origin-1',
  });
  const wrapper = setup();
  await buttonWithText(wrapper, 'Save as prospect').trigger('click');
  await flushPromises();
  expect(mocks.save).toHaveBeenCalledWith('rec-1', {
    assessment_revision_id: 'revision-1',
    request_key: 'same-request-key',
  });
  expect(wrapper.emitted('completed')?.[0]?.[0]).toMatchObject({
    kind: 'saved',
    message: expect.stringContaining('Saved as a prospect'),
  });
});

it('hides prospect saving while keeping the relevance decision available when prospects are disabled', () => {
  vi.stubEnv('VITE_HUGINN_PROSPECTS_ENABLED', 'false');
  const wrapper = setup();
  expect(wrapper.text()).not.toContain('Save as prospect');
  expect(buttonWithText(wrapper, 'Not relevant').exists()).toBe(true);
});
