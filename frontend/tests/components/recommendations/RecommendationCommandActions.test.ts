import { flushPromises, mount } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { beforeEach, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import Select from 'primevue/select';
import { ApiError } from '../../../src/api/apiError';
import RecommendationCommandActions from '../../../src/features/recommendations/components/RecommendationCommandActions.vue';
import type {
  RecommendationView,
  RecommendationPreferences,
} from '../../../src/features/recommendations/models/prospecting';

const mocks = vi.hoisted(() => ({
  save: vi.fn(),
  notRelevant: vi.fn(),
  later: vi.fn(),
  refreshPreferences: vi.fn(),
}));
vi.mock('../../../src/features/recommendations/api/saveRecommendation', () => ({
  saveRecommendation: mocks.save,
}));
vi.mock('../../../src/features/recommendations/api/markRecommendationNotRelevant', () => ({
  markRecommendationNotRelevant: mocks.notRelevant,
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
  mocks.refreshPreferences.mockResolvedValue(preferences);
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

it('preserves a rejected decision draft and retries only the exact same idempotent request after an uncertain response', async () => {
  mocks.notRelevant.mockRejectedValueOnce(new TypeError('network interrupted')).mockResolvedValue({
    recommendation_id: 'rec-1',
    recommendation_status: 'rejected',
    recommendation_version: 8,
    resolved_at: '2026-11-14T11:00:00Z',
    suppression_block_id: 'block-1',
    reason: 'Wrong buyer',
    remaining_blockers: ['rejected'],
  });
  const wrapper = setup();
  const reason = wrapper.get('textarea');
  await reason.setValue('Wrong buyer');
  await buttonWithText(wrapper, 'Not relevant').trigger('click');
  await flushPromises();
  expect(reason.element.value).toBe('Wrong buyer');
  expect((reason.element as HTMLTextAreaElement).disabled).toBe(true);
  expect(wrapper.text()).toContain('Retry the same update safely.');
  expect(wrapper.text()).not.toContain('request key');
  expect(wrapper.text()).not.toContain('receipt');
  const firstRequest = mocks.notRelevant.mock.calls[0];
  expect(firstRequest).toEqual([
    'rec-1',
    expect.objectContaining({
      assessment_revision_id: 'revision-1',
      expected_recommendation_version: 7,
      reason: 'Wrong buyer',
      request_key: 'same-request-key',
    }),
  ]);
  await buttonWithText(wrapper, 'Retry the same request').trigger('click');
  await flushPromises();
  expect(mocks.notRelevant).toHaveBeenCalledTimes(2);
  expect(mocks.notRelevant.mock.calls[1]).toEqual(firstRequest);
  expect(wrapper.emitted('completed')?.[0]?.[0]).toMatchObject({ kind: 'not_relevant' });
  expect(wrapper.emitted('completed')?.[0]?.[0]).toMatchObject({
    message: expect.stringContaining('persistent Company block'),
  });
});

it('retries an uncertain decision against its original recommendation target after a row prop changes', async () => {
  mocks.notRelevant.mockRejectedValueOnce(new TypeError('network interrupted')).mockResolvedValue({
    recommendation_id: 'rec-1',
    recommendation_status: 'rejected',
    recommendation_version: 8,
    resolved_at: '2026-11-14T11:00:00Z',
    suppression_block_id: 'block-1',
    reason: 'Wrong buyer',
    remaining_blockers: ['rejected'],
  });
  const wrapper = setup();
  await wrapper.get('textarea').setValue('Wrong buyer');
  await buttonWithText(wrapper, 'Not relevant').trigger('click');
  await flushPromises();

  const changedRecommendation = model();
  changedRecommendation.id = 'rec-2';
  const changedAssessment = changedRecommendation.assessment;
  if (!changedAssessment) throw new Error('Test recommendation needs an assessment');
  changedAssessment.id = 'revision-2';
  await wrapper.setProps({ recommendation: changedRecommendation });
  await buttonWithText(wrapper, 'Retry the same request').trigger('click');
  await flushPromises();

  expect(mocks.notRelevant.mock.calls[1]).toEqual(mocks.notRelevant.mock.calls[0]);
  expect(mocks.notRelevant.mock.calls[1]?.[0]).toBe('rec-1');
});

it('previews the Business cadence and explicitly confirms replacement of only the active pause', async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-14T10:00:00.000Z'));
  mocks.later.mockResolvedValue({
    recommendation_id: 'rec-1',
    recommendation_version: 8,
    pause_choice: 'x3',
    repeat_interval_days: 30,
    selected_at: '2026-11-14T10:00:00Z',
    expires_at: '2027-02-12T10:00:00Z',
    suppression_block_id: 'new-pause',
    replaced_pause_id: 'old-pause',
    remaining_blockers: ['rejected'],
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
  wrapper.getComponent(Select).vm.$emit('update:modelValue', 'x3');
  await flushPromises();
  expect(wrapper.text()).toContain('3 × 30-day repeat interval (90 days)');
  expect(wrapper.text()).toContain('replaces the current pause');
  await buttonWithText(wrapper, 'Review Later').trigger('click');
  await flushPromises();
  expect(mocks.refreshPreferences).toHaveBeenCalledTimes(1);
  expect(mocks.later).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain('If you pause now');
  expect(wrapper.text()).toContain('UTC');
  const preview = wrapper.get('[data-testid="later-expiry-preview"]').text();
  await vi.advanceTimersByTimeAsync(1000);
  await flushPromises();
  expect(wrapper.get('[data-testid="later-expiry-preview"]').text()).not.toBe(preview);
  await buttonWithText(wrapper, 'Confirm Later').trigger('click');
  await flushPromises();
  expect(mocks.refreshPreferences).toHaveBeenCalledTimes(2);
  expect(mocks.later).toHaveBeenCalledWith('rec-1', {
    assessment_revision_id: 'revision-1',
    expected_pause_id: 'old-pause',
    expected_pause_version: 3,
    expected_preference_updated_at: preferences.updated_at,
    expected_recommendation_version: 7,
    expected_repeat_interval_days: 30,
    pause_choice: 'x3',
    request_key: 'same-request-key',
  });
  expect(wrapper.emitted('completed')?.[0]?.[0]).toMatchObject({
    message: expect.stringContaining('Accepted at 2026-11-14 10:00:00.000 UTC'),
  });
  expect(wrapper.emitted('completed')?.[0]?.[0]).toMatchObject({ kind: 'later' });
  vi.useRealTimers();
});

it('keeps the selected Later duration and requires a second confirmation after cadence changes', async () => {
  mocks.refreshPreferences
    .mockResolvedValueOnce(preferences)
    .mockResolvedValueOnce({
      business_id: 'business-1',
      repeat_interval_days: 45,
      updated_at: '2026-11-14T11:00:00Z',
    })
    .mockResolvedValue({
      business_id: 'business-1',
      repeat_interval_days: 45,
      updated_at: '2026-11-14T11:00:00Z',
    });
  const wrapper = setup();
  wrapper.getComponent(Select).vm.$emit('update:modelValue', 'x2');
  await flushPromises();
  await buttonWithText(wrapper, 'Review Later').trigger('click');
  await flushPromises();
  expect(wrapper.text()).toContain('2 × 30-day repeat interval (60 days)');
  await buttonWithText(wrapper, 'Confirm Later').trigger('click');
  await flushPromises();
  expect(mocks.later).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain('Business repeat timing changed');
  expect(wrapper.text()).toContain('2 × 45-day repeat interval (90 days)');
  await buttonWithText(wrapper, 'Confirm Later').trigger('click');
  await flushPromises();
  expect(mocks.later).toHaveBeenCalledWith(
    'rec-1',
    expect.objectContaining({
      expected_preference_updated_at: '2026-11-14T11:00:00Z',
      expected_repeat_interval_days: 45,
      pause_choice: 'x2',
    }),
  );
});

it('retains an editable stale decision draft until the user refreshes server state', async () => {
  mocks.notRelevant.mockRejectedValue(new ApiError(409, 'conflict', 'stale version'));
  const wrapper = setup();
  const reason = wrapper.get('textarea');
  await reason.setValue('Wrong buyer');
  await buttonWithText(wrapper, 'Not relevant').trigger('click');
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
