import { mount, flushPromises } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import PrimeVue from 'primevue/config';
import RecommendationFeedbackForm from '../../src/features/recommendations/components/RecommendationFeedbackForm.vue';
const save = vi.hoisted(() => vi.fn());
vi.mock('../../src/features/recommendations/api/saveRecommendationFeedback', () => ({
  saveRecommendationFeedback: save,
}));
beforeEach(() => {
  save.mockReset();
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
});
it('preserves corrections after failure and appends feedback without replacing history', async () => {
  save
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({ id: 'feedback-2', batch_id: 'batch-1', recommendation_id: 'rec-1' });
  const wrapper = mount(RecommendationFeedbackForm, {
    props: {
      batchId: 'batch-1',
      recommendationId: 'rec-1',
      history: [
        {
          id: 'feedback-1',
          batch_id: 'batch-1',
          recommendation_id: 'rec-1',
          created_at: '2026-10-28T00:00:00Z',
          usefulness: 'useful',
          reasons: [],
          correction: '',
          next_step: 'research',
          outcome: 'not_contacted',
          notes: 'Earlier assessment',
        },
      ],
    },
    global: { plugins: [PrimeVue] },
  });
  await wrapper.get('textarea[maxlength="2000"]').setValue('Actually a supplier');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('Feedback could not be saved');
  expect((wrapper.get('textarea[maxlength="2000"]').element as HTMLTextAreaElement).value).toBe(
    'Actually a supplier',
  );
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(save.mock.calls[1]?.[0]).toBe('batch-1');
  expect(save.mock.calls[1]?.[1]).toMatchObject({
    recommendation_id: 'rec-1',
    correction: 'Actually a supplier',
  });
  expect(wrapper.text()).toContain('Feedback saved');
  expect(wrapper.text()).toContain('Earlier assessment');
  expect(wrapper.emitted('saved')).toHaveLength(1);
});

it('rejects feedback receipts from a different batch and preserves the draft', async () => {
  save.mockResolvedValue({ id: 'feedback-2', batch_id: 'other-batch', recommendation_id: 'rec-1' });
  const wrapper = mount(RecommendationFeedbackForm, {
    props: { batchId: 'batch-1', recommendationId: 'rec-1', history: [] },
    global: { plugins: [PrimeVue] },
  });
  await wrapper.get('textarea[maxlength="2000"]').setValue('Correction for this batch');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(wrapper.text()).toContain('Feedback could not be saved');
  expect(wrapper.emitted('saved')).toBeUndefined();
  expect((wrapper.get('textarea[maxlength="2000"]').element as HTMLTextAreaElement).value).toBe(
    'Correction for this batch',
  );
});
