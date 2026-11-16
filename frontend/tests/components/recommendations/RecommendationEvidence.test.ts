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

  expect(wrapper.text()).toContain('Currently blocked by an independent decision or relationship');
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
