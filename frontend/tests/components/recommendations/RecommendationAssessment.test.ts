import { mount } from '@vue/test-utils';
import { expect, it } from 'vitest';
import type { components } from '../../../src/api/generated/schema';
import RecommendationAssessment from '../../../src/features/recommendations/components/RecommendationAssessment.vue';

const assessment: components['schemas']['AssessmentRevisionResponse'] = {
  id: 'revision-1',
  recommendation_id: 'recommendation-1',
  business_id: 'business-1',
  company_id: 'company-1',
  revision_number: 2,
  assessed_at: '2026-11-01T10:00:00Z',
  assessed_by_user_id: 'user-1',
  strategy_assessments: [
    {
      strategy_id: 'strategy-1',
      offering_id: 'offering-1',
      ideal_client_profile_id: 'icp-1',
      strategy_snapshot: { name: 'Research strategy' },
      offering_snapshot: { name: 'Product research' },
      ideal_client_profile_snapshot: { name: 'Research teams' },
      assessment_snapshot: {
        rationale: 'Current hiring suggests a research workflow review.',
        unknowns: ['Buying role is unknown.'],
        evidence: [
          {
            observation_id: 'observation-1',
            quote: 'We are adding two analysts.',
          },
        ],
        company_facts: { country: 'US' },
      },
    },
  ],
  professional_profile_snapshot: { headline: 'Research consulting' },
  evidence_snapshots: [
    {
      observation_id: 'observation-1',
      quote: 'We are adding two analysts.',
      source: 'company website',
      source_url: 'https://northstar.example/careers',
      occurred_at: '2026-10-30T00:00:00Z',
      observed_at: '2026-11-01T10:00:00Z',
    },
  ],
  evidence_observation_ids: ['observation-1'],
  policy_versions: ['fit-v1'],
  evaluation_seed: 'fixture-seed',
};

it('renders the immutable origin assessment and joins source details by observation ID', () => {
  const wrapper = mount(RecommendationAssessment, {
    props: { assessment, heading: 'Assessment at this prospect’s origin' },
  });
  expect(wrapper.text()).toContain('Assessment at this prospect’s origin');
  expect(
    wrapper.get('[data-assessment-revision-id]').attributes('data-assessment-revision-id'),
  ).toBe('revision-1');
  expect(wrapper.text()).toContain('Current hiring suggests a research workflow review.');
  expect(wrapper.text()).not.toContain('Buying role is unknown.');
  expect(wrapper.text()).not.toContain('Product research');
  expect(wrapper.text()).not.toContain('Research strategy');
  expect(wrapper.get('a').attributes('href')).toBe('https://northstar.example/careers');
  expect(wrapper.text()).toContain('Source date:');
  expect(wrapper.text()).not.toContain('Current source evidence differs');
});
