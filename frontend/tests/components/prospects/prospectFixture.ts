import type { components } from '../../../src/api/generated/schema';

export type Prospect = components['schemas']['ProspectResponse'];
export type Activity = components['schemas']['ProspectActivityResponse'];

export function prospect(overrides: Partial<Prospect> = {}): Prospect {
  return {
    id: 'prospect-1',
    business_id: 'business-1',
    company_id: 'company-1',
    company: {
      name: 'Northstar Research',
      domain: 'northstar.example',
      country: 'US',
      business_sector: ['Research'],
      company_scale: '11-50',
      company_status: 'active',
    },
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
    stage: 'in_conversation',
    last_active_stage: null,
    notes: 'Current customer need is unclear.',
    follow_up_at: null,
    version: 4,
    origins: [],
    activities: [],
    ...overrides,
  };
}

export function activity(overrides: Partial<Activity> = {}): Activity {
  return {
    id: 'activity-1',
    business_id: 'business-1',
    prospect_id: 'prospect-1',
    actor_user_id: 'user-1',
    kind: 'stage_changed',
    occurred_at: '2026-11-01T10:00:00Z',
    effective_occurred_at: '2026-11-01T10:00:00Z',
    recorded_at: '2026-11-01T10:01:00Z',
    payload: { prior_stage: 'contacted', new_stage: 'in_conversation', reason: null },
    correction_of_id: null,
    correction_head_id: null,
    correction_sequence: 0,
    ...overrides,
  };
}
