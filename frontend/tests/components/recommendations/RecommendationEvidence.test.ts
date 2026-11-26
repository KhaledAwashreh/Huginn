import { mount } from '@vue/test-utils';
import { defineComponent, h } from 'vue';
import { expect, it } from 'vitest';
import RecommendationEvidence from '../../../src/features/recommendations/components/RecommendationEvidence.vue';
import type { RecommendationView } from '../../../src/features/recommendations/models/prospecting';

function recommendation(overrides: Partial<RecommendationView> = {}): RecommendationView {
  return {
    id: 'same-recommendation',
    current_revision_id: 'revision-1',
    first_presented_at: null,
    assessment_presented_at: null,
    status: 'open',
    current_eligibility: 'not_reassessed',
    evidence_state: 'not_assessed',
    selection_blockers: [],
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
    active_blocks: [],
    company: {
      name: 'Northstar',
      domain: 'northstar.example',
      country: 'US',
      business_sector: ['Research'],
      company_scale: '11-50',
      company_status: 'active',
    },
    assessment: null,
    prospect: null,
    business_id: 'business-1',
    company_id: 'company-1',
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-01T10:00:00Z',
    resolved_at: null,
    resolved_by_user_id: null,
    resolution_reason: null,
    version: 1,
    read_at: '2026-11-01T10:00:00Z',
    ...overrides,
  } as RecommendationView;
}

it('renders replaced canonical props for the same recommendation identity', async () => {
  const wrapper = mount(RecommendationEvidence, {
    props: { recommendation: recommendation() },
  });
  await wrapper.setProps({
    recommendation: recommendation({
      current_eligibility: 'blocked',
      company: {
        name: 'Northstar updated',
        domain: 'northstar.example',
        country: 'CA',
        business_sector: ['Research'],
        company_scale: '11-50',
        company_status: 'active',
      },
    }),
  });

  expect(wrapper.text()).not.toContain('Currently blocked');
  expect(wrapper.text()).toContain('Northstar updated');
  expect(wrapper.text()).toContain('CA');
});

it('keeps heading associations unique when the same recommendation is shown twice', () => {
  const pair = defineComponent({
    setup: () => () =>
      h('div', [
        h(RecommendationEvidence, { recommendation: recommendation() }),
        h(RecommendationEvidence, { recommendation: recommendation() }),
      ]),
  });
  const wrapper = mount(pair);
  const ids = wrapper.findAll('h2').map((heading) => heading.attributes('id'));
  expect(ids[0]).toBeTruthy();
  expect(ids[1]).toBeTruthy();
  expect(new Set(ids).size).toBe(2);
});

it('keeps a compact summary visible while company info and signals are collapsed', () => {
  const wrapper = mount(RecommendationEvidence, {
    props: {
      recommendation: recommendation({
        company: { ...recommendation().company, description: 'Tools for research teams.' },
      }),
    },
  });
  expect(wrapper.get('details').attributes('open')).toBeUndefined();
  expect(wrapper.get('summary').text()).toContain('Northstar');
  expect(wrapper.get('summary').text()).toContain('Tools for research teams.');
  expect(wrapper.get('summary').text()).toContain('View company & signals');
  expect(wrapper.text()).not.toContain('Current company context');
  expect(wrapper.text()).not.toContain('These fields describe the company now.');
  expect(wrapper.text()).toContain('Company info');
});

it('hides scoring while preserving selected-strategy signals and the visible revision marker', () => {
  const item = recommendation();
  item.assessment = {
    id: 'shown-revision',
    strategy_assessments: [
      {
        strategy_id: 'strategy-a',
        assessment_snapshot: {
          score: 84,
          confidence: 'low',
          evidence: [{ quote: 'Selected strategy signal.' }],
        },
      },
      {
        strategy_id: 'strategy-b',
        assessment_snapshot: { score: 32, evidence: [{ quote: 'Other strategy signal.' }] },
      },
    ],
    evidence_snapshots: [],
  } as unknown as NonNullable<RecommendationView['assessment']>;
  const wrapper = mount(RecommendationEvidence, {
    props: { recommendation: item, strategyId: 'strategy-a' },
  });
  expect(wrapper.text()).not.toMatch(/Relevance|Confidence|\d+\/100/);
  expect(wrapper.text()).toContain('Selected strategy signal.');
  expect(wrapper.text()).not.toContain('Other strategy signal.');
  expect(wrapper.findAll('[data-assessment-revision-id="shown-revision"]')).toHaveLength(1);
  const marker = wrapper.get('[data-assessment-revision-id="shown-revision"]');
  expect(marker.element.closest('details')).toBeNull();
});
