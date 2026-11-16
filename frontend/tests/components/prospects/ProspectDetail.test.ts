import { mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { expect, it } from 'vitest';
import ProspectDetail from '../../../src/features/prospects/components/ProspectDetail.vue';
import { createProspectCommandDraft } from '../../../src/features/prospects/models/prospectCommandDraft';
import { prospect } from './prospectFixture';

const saved = prospect({
  current_source_context: {
    evidence_state: 'changed',
    has_more: false,
    signals: [
      {
        id: 'current-signal',
        observation_id: 'current-observation',
        signal_type: 'other',
        source: 'eu_startups',
        source_url: 'https://example.test/current',
        description: 'Present source says the company now builds career tools.',
        stage: null,
        occurred_at: '2026-11-12T09:00:00Z',
        observed_at: '2026-11-13T10:00:00Z',
        ingested_at: '2026-11-13T11:00:00Z',
        evidence_kind: 'directory_context',
        hiring_state: 'not_applicable',
      },
    ],
  },
  origins: [
    {
      id: 'origin-1',
      business_id: 'business-1',
      company_id: 'company-1',
      prospect_id: 'prospect-1',
      recommendation_id: 'recommendation-1',
      assessment_revision_id: 'revision-1',
      created_by_user_id: 'user-1',
      created_at: '2026-11-01T10:00:00Z',
      recommendation_status: 'converted',
      recommendation_version: 2,
      assessment: {
        id: 'revision-1',
        recommendation_id: 'recommendation-1',
        business_id: 'business-1',
        company_id: 'company-1',
        revision_number: 1,
        assessed_at: '2026-11-01T09:00:00Z',
        assessed_by_user_id: 'user-1',
        strategy_assessments: [
          {
            strategy_id: 'strategy-1',
            offering_id: 'offering-1',
            ideal_client_profile_id: 'icp-1',
            strategy_snapshot: { name: 'Original strategy' },
            offering_snapshot: {},
            ideal_client_profile_snapshot: {},
            assessment_snapshot: {
              evidence: [
                { observation_id: 'original-observation', quote: 'Original assessment excerpt.' },
              ],
            },
          },
        ],
        professional_profile_snapshot: {},
        evidence_snapshots: [
          { observation_id: 'original-observation', quote: 'Original assessment excerpt.' },
        ],
        evidence_observation_ids: ['original-observation'],
        policy_versions: [],
        evaluation_seed: 'seed',
      },
    },
  ],
});

function detail(value = saved) {
  return mount(ProspectDetail, {
    props: {
      prospect: value,
      draft: createProspectCommandDraft(value.id),
      disabled: false,
      pending: false,
      commandError: '',
      canRetry: false,
      needsRefresh: false,
      completionMessage: '',
    },
    global: { plugins: [PrimeVue] },
  });
}

it('separates current guarded source text and lineage from the retained assessment', () => {
  const wrapper = detail();
  const current = wrapper.get('[aria-label="Current guarded source context"]');
  expect(current.text()).toContain('Present source says the company now builds career tools.');
  expect(current.text()).toContain('differs from the evidence saved with this prospect');
  expect(current.text()).toContain('has not been reassessed');
  expect(current.get('a').attributes('href')).toBe('https://example.test/current');
  expect(current.findAll('time').map((time) => time.attributes('datetime'))).toEqual([
    '2026-11-12T09:00:00Z',
    '2026-11-13T10:00:00Z',
    '2026-11-13T11:00:00Z',
  ]);
  expect(current.text()).not.toContain('Original assessment excerpt.');
  expect(wrapper.get('.origins').text()).toContain('Original assessment excerpt.');
  expect(wrapper.find('[data-observation-id="current-observation"]').exists()).toBe(true);
});

it('keeps origin evidence readable when current guarded sources become unavailable', () => {
  const wrapper = detail(
    prospect({
      ...saved,
      current_source_context: { signals: [], has_more: false, evidence_state: 'unavailable' },
    }),
  );
  expect(wrapper.get('[aria-label="Current guarded source context"]').text()).toContain(
    'Current source evidence is unavailable',
  );
  expect(wrapper.get('.origins').text()).toContain('Original assessment excerpt.');
});

function currentSourceFixture() {
  const context = saved.current_source_context;
  if (!context) throw new Error('Expected current source fixture context');
  const signal = context.signals[0];
  if (!signal) throw new Error('Expected a current source fixture signal');
  return { context, signal };
}

it('discloses the source bound and rejects unsafe current-source links', () => {
  const { context, signal } = currentSourceFixture();
  const wrapper = detail(
    prospect({
      ...saved,
      current_source_context: {
        ...context,
        has_more: true,
        signals: [{ ...signal, source_url: 'javascript:alert(1)' }],
      },
    }),
  );
  const current = wrapper.get('[aria-label="Current guarded source context"]');
  expect(current.text()).toContain('Showing the first 50 current sources');
  expect(current.find('a').exists()).toBe(false);
});

it('shows an unknown source date while preserving observation and ingestion times', () => {
  const { context, signal } = currentSourceFixture();
  const wrapper = detail(
    prospect({
      ...saved,
      current_source_context: {
        ...context,
        signals: [{ ...signal, occurred_at: null }],
      },
    }),
  );
  const current = wrapper.get('[aria-label="Current guarded source context"]');
  const sourceDate = current.get('dl > div');
  expect(sourceDate.get('dt').text()).toBe('Source date');
  expect(sourceDate.get('dd').text()).toBe('Unknown');
  expect(sourceDate.find('time').exists()).toBe(false);
  expect(current.findAll('time').map((time) => time.attributes('datetime'))).toEqual([
    '2026-11-13T10:00:00Z',
    '2026-11-13T11:00:00Z',
  ]);
});
