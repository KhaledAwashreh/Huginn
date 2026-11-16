import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import RecommendationQualityFeedback from '../../../src/features/recommendations/components/RecommendationQualityFeedback.vue';
import { createRecommendationCommandDraft } from '../../../src/features/recommendations/models/recommendationCommandDraft';
import { ApiError } from '../../../src/api/apiError';
import type { RecommendationView } from '../../../src/features/recommendations/models/prospecting';

const mocks = vi.hoisted(() => ({ record: vi.fn() }));
vi.mock('../../../src/features/recommendations/api/recordRecommendationFeedback', () => ({
  recordRecommendationFeedback: mocks.record,
}));

function recommendation(id = 'rec-1', revisionId = 'revision-1'): RecommendationView {
  return {
    id,
    assessment: { id: revisionId },
  } as RecommendationView;
}
function setup() {
  return mount(RecommendationQualityFeedback, {
    props: {
      recommendation: recommendation(),
      identity: 'account-1:user-1:csrf-1',
      draftState: createRecommendationCommandDraft('rec-1'),
    },
    global: { plugins: [PrimeVue] },
  });
}
function button(wrapper: ReturnType<typeof setup>, name: string) {
  const found = wrapper.findAll('button').find((candidate) => candidate.text() === name);
  if (!found) throw new Error(`Button "${name}" was not found`);
  return found;
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'report-key') });
});

it('submits a report for the exact shown assessment without changing decision state', async () => {
  mocks.record.mockResolvedValue({ id: 'feedback-1', assessment_revision_id: 'revision-1' });
  const wrapper = setup();
  await wrapper.get('select').setValue('not_useful');
  await wrapper.get('input[value="evidence_wrong"]').setValue(true);
  const textareas = wrapper.findAll('textarea');
  const notes = textareas[1];
  if (!notes) throw new Error('Notes field was not rendered');
  await notes.setValue('Evidence is no longer current.');
  await wrapper.get('form').trigger('submit');
  await flushPromises();

  expect(mocks.record).toHaveBeenCalledWith('rec-1', {
    assessment_revision_id: 'revision-1',
    request_key: 'report-key',
    feedback: {
      usefulness: 'not_useful',
      reasons: ['evidence_wrong'],
      outcome: 'unknown',
      next_step: 'none',
      correction: '',
      notes: 'Evidence is no longer current.',
    },
  });
  expect(wrapper.text()).toContain(
    'This report does not change your recommendation or its ranking.',
  );
  expect(wrapper.text()).not.toContain('Feedback recorded for assessment revision');
});

it('retries an uncertain report against its original recommendation and exact revision', async () => {
  mocks.record
    .mockRejectedValueOnce(new TypeError('network interrupted'))
    .mockResolvedValue({ id: 'feedback-1' });
  const wrapper = setup();
  await wrapper.get('select').setValue('useful');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  const original = mocks.record.mock.calls[0];

  await wrapper.setProps({ recommendation: recommendation('rec-2', 'revision-2') });
  await button(wrapper, 'Retry the same report').trigger('click');
  await flushPromises();
  expect(mocks.record.mock.calls[1]).toEqual(original);
  expect(mocks.record.mock.calls[1]?.[0]).toBe('rec-1');
  expect(mocks.record.mock.calls[1]?.[1].assessment_revision_id).toBe('revision-1');
});

it('discards unsubmitted form values on leaving while preserving a separate decision draft', async () => {
  const wrapper = setup();
  const draft = wrapper.props('draftState');
  draft.snapshot = recommendation();
  draft.reason = 'Keep this decision reason.';
  await wrapper.get('select').setValue('not_useful');
  await wrapper.get('input[value="evidence_wrong"]').setValue(true);
  const notes = wrapper.findAll('textarea')[1];
  if (!notes) throw new Error('Notes field was not rendered');
  await notes.setValue('Temporary notes.');
  wrapper.unmount();
  expect(draft.feedback).toEqual(createRecommendationCommandDraft('rec-1').feedback);
  expect(draft.reason).toBe('Keep this decision reason.');
  expect(draft.snapshot?.id).toBe('rec-1');
  expect(mocks.record).not.toHaveBeenCalled();
});

it('discards a rejected report when leaving the form', async () => {
  mocks.record.mockRejectedValue(new ApiError(422, 'validation_error', 'Invalid report'));
  const wrapper = setup();
  const draft = wrapper.props('draftState');
  await wrapper.get('select').setValue('not_useful');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(draft.feedback.status).toBe('error');
  wrapper.unmount();
  expect(draft.feedback).toEqual(createRecommendationCommandDraft('rec-1').feedback);
  expect(draft.snapshot).toBeNull();
});

it.each(['pending', 'uncertain'] as const)(
  'preserves a submitted %s report on leaving for exact-request retry',
  async (status) => {
    if (status === 'pending') mocks.record.mockReturnValue(new Promise(() => {}));
    else mocks.record.mockRejectedValue(new TypeError('network interrupted'));
    const wrapper = setup();
    const draft = wrapper.props('draftState');
    await wrapper.get('select').setValue('useful');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    const intent = draft.feedback.intent;
    expect(draft.feedback.status).toBe(status);
    wrapper.unmount();
    expect(draft.feedback.intent).toBe(intent);
    expect(draft.feedback.usefulness).toBe('useful');
    expect(draft.feedback.status).toBe(status);
    expect(draft.snapshot?.id).toBe('rec-1');
  },
);
