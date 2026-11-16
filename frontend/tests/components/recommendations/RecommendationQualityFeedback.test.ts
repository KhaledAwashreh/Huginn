import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import RecommendationQualityFeedback from '../../../src/features/recommendations/components/RecommendationQualityFeedback.vue';
import { createRecommendationCommandDraft } from '../../../src/features/recommendations/models/recommendationCommandDraft';
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
  await button(wrapper, 'Report assessment quality').trigger('click');
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
  expect(wrapper.text()).toContain('It did not change recommendation status or ranking');
});

it('retries an uncertain report against its original recommendation and exact revision', async () => {
  mocks.record
    .mockRejectedValueOnce(new TypeError('network interrupted'))
    .mockResolvedValue({ id: 'feedback-1' });
  const wrapper = setup();
  await button(wrapper, 'Report assessment quality').trigger('click');
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
