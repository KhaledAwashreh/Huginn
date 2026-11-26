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
const strategy = assessment.strategy_assessments[0];
if (!strategy) throw new Error('The fixture requires a strategy assessment.');

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

it.each([0, 78, 100])('hides retained scoring %s while keeping rationale and evidence', (score) => {
  const wrapper = mount(RecommendationAssessment, {
    props: {
      assessment: {
        ...assessment,
        strategy_assessments: [
          {
            ...strategy,
            assessment_snapshot: { ...strategy.assessment_snapshot, score, confidence: 'low' },
          },
        ],
      },
    },
  });
  expect(wrapper.text()).not.toMatch(/Relevance|Confidence|\d+\/100/);
  expect(wrapper.text()).toContain('Current hiring suggests a research workflow review.');
  expect(wrapper.text()).toContain('We are adding two analysts.');
});

it('keeps multiple offering assessments readable without exposing strategy names or scores', () => {
  const wrapper = mount(RecommendationAssessment, {
    props: {
      assessment: {
        ...assessment,
        strategy_assessments: [
          { ...strategy, assessment_snapshot: { ...strategy.assessment_snapshot, score: 78 } },
          {
            ...strategy,
            strategy_id: 'strategy-2',
            strategy_snapshot: { name: 'Engineering strategy' },
            offering_snapshot: { name: 'Engineering services' },
            assessment_snapshot: { ...strategy.assessment_snapshot, score: 91 },
          },
        ],
      },
    },
  });
  expect(wrapper.findAll('h4').map((item) => item.text())).toEqual([
    'Product research',
    'Engineering services',
  ]);
  expect(wrapper.text()).not.toMatch(/Relevance|Confidence|\d+\/100/);
});

it('shows company signals without rationale boilerplate or raw company metadata in recommendation cards', () => {
  const wrapper = mount(RecommendationAssessment, {
    props: { assessment, signalsOnly: true },
  });
  expect(wrapper.text()).toContain('Company signals');
  expect(wrapper.text()).toContain('We are adding two analysts.');
  expect(wrapper.text()).not.toContain('Current hiring suggests');
  expect(wrapper.text()).not.toContain('Current source evidence');
  expect(wrapper.text()).not.toContain('Assessment-time');
  expect(wrapper.find('pre').exists()).toBe(false);
});

// Public source snapshots retained in the audited assessment revisions.
const retainedSources = [
  {
    company: 'Rootly',
    quote:
      'Rootly | https://rootly.com/ | design, engineering, GTM, sales | SF Bay, Toronto, APAC, Remote\nOn-call, incident response, and AI SRE. Trusted by leading companies like',
    source: 'hn',
    source_url: 'https://news.ycombinator.com/item?id=49926195',
    description:
      'Rootly | https://rootly.com/ | design, engineering, GTM, sales | SF Bay, Toronto, APAC, Remote\nOn-call, incident response, and AI SRE. Trusted by leading companies like NVIDIA, Dropbox, Canva, Figma, and more.\nHiring across marketing, engineering, product, GTM, and sales https://rootly.com/careers',
    observed_at: '2026-11-02T09:31:41.742261+00:00',
    occurred_at: '2026-10-01T19:43:21+00:00',
    observation_id: '19e2094b-3e32-4b61-bd05-625c660164fb',
    source_country: null,
  },
  {
    company: 'Edgerun',
    quote:
      'Military exoskeletons\n\nEdgerun builds military exoskeletons. The first product is a 10-pound hip system that fits over existing kit and doubles a soldier’s range. Since',
    source: 'yc',
    source_url: 'https://www.ycombinator.com/companies/edgerun',
    description:
      'Military exoskeletons\n\nEdgerun builds military exoskeletons. The first product is a 10-pound hip system that fits over existing kit and doubles a soldier’s range. Since April 2026, Edgerun built over a dozen iterations of their product through continuous field tests with Ukrainian fighters and secured $150M+ in LOIs. Founder David Venegas previously co-founded Durin (autonomous mining robotics) and worked at Stoke Space (at 19) and Hadrian. He is a high-school dropout, state-championship runner, adventure athlete, and pilot. Edgerun is a Y Combinator company backed by General H.R. McMaster, Cyan Banister, Joshua Steinman and Jason Miller. edgerun.com',
    observed_at: '2026-11-02T09:32:45.851456+00:00',
    occurred_at: '2026-08-21T20:22:39+00:00',
    observation_id: 'f974e95e-c607-4bed-8172-10b37b7b1130',
    source_country: null,
  },
];

function withSource(source: Record<string, unknown>) {
  return {
    ...assessment,
    strategy_assessments: assessment.strategy_assessments.map((item) => ({
      ...item,
      assessment_snapshot: {
        evidence: [{ observation_id: source.observation_id, quote: source.quote }],
      },
    })),
    evidence_snapshots: [source],
  };
}

it.each(retainedSources)(
  'shows the complete retained $company source on cards while preserving the historical assessment quote',
  (source) => {
    const retainedAssessment = withSource(source);
    const card = mount(RecommendationAssessment, {
      props: { assessment: retainedAssessment, signalsOnly: true },
    });
    expect(card.get('blockquote').element.textContent).toBe(source.description);
    expect(card.get('a').attributes('href')).toBe(source.source_url);
    expect(card.get('a').text()).toBe(source.source === 'hn' ? 'Hacker News' : 'YC profile');
    expect(card.get('time').attributes('datetime')).toBe(source.occurred_at);
    expect(card.get('time').text()).not.toContain('UTC');
    expect(card.get('time').text()).toContain('2026');

    const historical = mount(RecommendationAssessment, {
      props: { assessment: retainedAssessment },
    });
    expect(historical.get('blockquote').element.textContent).toBe(source.quote);
    expect(historical.get('a').attributes('href')).toBe(source.source_url);
    expect(historical.get('time').text()).toContain('UTC');
  },
);

it.each([undefined, null, '', '   '])(
  'falls back to the retained quote for legacy descriptions: %s',
  (description) => {
    const wrapper = mount(RecommendationAssessment, {
      props: {
        assessment: withSource({ observation_id: 'legacy', description, quote: 'Legacy excerpt.' }),
        signalsOnly: true,
      },
    });
    expect(wrapper.get('blockquote').text()).toBe('Legacy excerpt.');
  },
);

it('shows unavailable evidence and keeps unsafe source URLs unlinked', () => {
  const wrapper = mount(RecommendationAssessment, {
    props: {
      assessment: withSource({ observation_id: 'legacy', source_url: 'javascript:alert(1)' }),
      signalsOnly: true,
    },
  });
  expect(wrapper.get('blockquote').text()).toBe('Source excerpt unavailable.');
  expect(wrapper.find('a').exists()).toBe(false);
  expect(wrapper.text()).toContain('Source link unavailable');
});

it('keeps legacy assessments readable without exposing internal strategy names', () => {
  const wrapper = mount(RecommendationAssessment, {
    props: {
      assessment: {
        ...assessment,
        strategy_assessments: [
          strategy,
          {
            ...strategy,
            strategy_id: 'other',
            strategy_snapshot: { name: 'Hidden legacy strategy' },
          },
        ],
      },
    },
  });
  expect(wrapper.text()).not.toContain('Research strategy');
  expect(wrapper.text()).not.toContain('Hidden legacy strategy');
  expect(wrapper.html()).not.toContain('Evidence for Research strategy');
  expect(wrapper.findAll('.strategy-assessment')).toHaveLength(2);
  expect(wrapper.findAll('h4').map((item) => item.text())).toEqual([
    'Product research',
    'Product research',
  ]);
  expect(wrapper.text()).toContain('Current hiring suggests');
});
