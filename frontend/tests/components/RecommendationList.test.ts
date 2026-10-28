import { mount } from '@vue/test-utils';
import { expect, it } from 'vitest';
import RecommendationList from '../../src/features/recommendations/components/RecommendationList.vue';
import type { RecommendationBatch } from '../../src/features/recommendations/models/recommendation';
it('shows company attributes frozen in the assessment, with explicit unknowns and source dates', () => {
  const batch: RecommendationBatch = {
    id: 'batch-1',
    strategy_id: 'strategy-1',
    created_at: '2026-10-28T00:00:00Z',
    algorithm_version: 'v1',
    assessment_method: 'Research relevance',
    candidate_count: 2,
    retrieval_limit: 10,
    items: [
      {
        id: 'rec-1',
        company: {
          id: 'company-1',
          name: 'Research company',
          domain: 'example.com',
          country: 'US',
          business_sector: ['Infrastructure', 'Developer tools'],
          company_scale: 'small',
        },
        score: 34,
        confidence: 'low',
        selection_type: 'exploration',
        rationale: 'Research fit',
        unknowns: [],
        breakdown: { service_fit: 12, business_context: 0, company_preferences: 10, timing: 12 },
        evidence: [
          {
            quote: 'Stored evidence',
            source_url: 'https://example.com/source',
            occurred_at: '2026-01-01T00:00:00Z',
            observed_at: '2026-10-01T00:00:00Z',
          },
        ],
      },
      {
        id: 'rec-2',
        company: {
          id: 'company-2',
          name: 'Sparse company',
          domain: 'sparse.example.com',
          country: null,
          business_sector: null,
          company_scale: null,
        },
        score: 12,
        confidence: 'low',
        selection_type: 'exploration',
        rationale: 'Limited context',
        unknowns: [],
        breakdown: { service_fit: 12, business_context: 0, company_preferences: 0, timing: 0 },
        evidence: [],
      },
    ],
  };
  const wrapper = mount(RecommendationList, {
    props: { batch, feedback: [], feedbackAvailable: true },
    global: { stubs: { RecommendationFeedbackForm: true } },
  });
  const contexts = wrapper.findAll('[aria-label="Company context at assessment"]');
  expect(contexts).toHaveLength(2);
  expect(contexts[0]?.text()).toContain('US');
  expect(contexts[0]?.text()).toContain('Infrastructure, Developer tools');
  expect(contexts[0]?.text()).toContain('small');
  expect(contexts[0]?.text()).toContain('recorded when this assessment was generated');
  expect(contexts[1]?.text().match(/Unknown/g)).toHaveLength(3);
  expect(wrapper.find('time[datetime="2026-01-01T00:00:00Z"]').exists()).toBe(true);
});
