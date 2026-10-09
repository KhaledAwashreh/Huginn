import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import MatchmakingProgress from '@/features/matchmaking/components/MatchmakingProgress.vue';
import type { components } from '@/api/generated/schema';

type RunDetail = components['schemas']['RunDetailResponse'];
const run: RunDetail = {
  as_of: '2026-10-09T12:00:00Z',
  counts_complete: false,
  created_matches_count: null,
  current_user_id: '1f891e25-047d-4c76-bf6d-701c28e47b31',
  cutoff: '2026-09-09T12:00:00Z',
  existing_matches_skipped_count: null,
  failed_count: 1,
  finished_at: null,
  heartbeat_at: '2026-10-09T12:01:00Z',
  id: '2f891e25-047d-4c76-bf6d-701c28e47b31',
  not_executed_count: 2,
  request_id: '3f891e25-047d-4c76-bf6d-701c28e47b31',
  requested_at: '2026-10-09T12:00:00Z',
  requester_account_id: '4f891e25-047d-4c76-bf6d-701c28e47b31',
  safe_error_code: null,
  settled_target_count: 3,
  skipped_count: 0,
  started_at: '2026-10-09T12:00:10Z',
  state: 'running',
  succeeded_count: 2,
  target_count: 5,
  target_kind: 'all_eligible',
  tracking_stale: false,
  uncertain_count: 0,
};

describe('matchmaking progress projections', () => {
  it('labels settled users as processed, keeps unknown totals unknown, and exposes current user activity', () => {
    const wrapper = mount(MatchmakingProgress, { props: { run } });
    const progress = wrapper.get('progress');

    expect(progress.attributes('aria-valuetext')).toBe('3 of 5 users processed');
    expect(wrapper.text()).toContain('Processed does not mean matched.');
    expect(wrapper.text()).toContain('Matcher is currently evaluating user');
    expect(wrapper.text()).toContain('Created matchesUnknown');
    expect(wrapper.text()).toContain('Existing matches skippedUnknown');
    expect(wrapper.text()).toContain('3 / 5 users processed');
  });
});
