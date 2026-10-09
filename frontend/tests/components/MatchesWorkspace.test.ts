import { mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { components } from '@/api/generated/schema';
import { ApiError } from '@/api/apiError';
import MatchOverviewEmptyState from '@/features/matches/components/MatchOverviewEmptyState.vue';
import MatchesPage from '@/features/matches/pages/MatchesPage.vue';
import MatchDetailPage from '@/features/matches/pages/MatchDetailPage.vue';

type Match = components['schemas']['UserMatchResponse'];
type Overview = components['schemas']['MatchesOverviewResponse'];
const companyMatch: Match = {
  id: 'match-001',
  status: 'new',
  created_at: '2026-10-09T12:00:00Z',
  updated_at: '2026-10-09T12:00:00Z',
  notes: null,
  company: {
    name: 'Example Company',
    domain: 'example.com',
    business_sector: ['Software'],
    country: 'US',
    company_scale: 'small',
    company_status: 'active',
  },
};
const overviewWithoutMatches: Overview = {
  has_matches: false,
  has_active_strategies: true,
  latest_evaluation: null,
};

const state = vi.hoisted(() => ({
  status: undefined as string | undefined,
  offset: 0,
  page: { items: [] as Match[], limit: 50, offset: 0, has_more: false },
  overview: {
    has_matches: false,
    has_active_strategies: true,
    latest_evaluation: null,
  } as Overview,
  setStatus: vi.fn(),
  setOffset: vi.fn(),
  previousPage: vi.fn(),
  nextPage: vi.fn(),
  retryMatches: vi.fn(),
  listPending: false,
  listErrorFlag: false,
  listError: undefined as unknown,
  retryOverview: vi.fn(),
  overviewErrorFlag: false,
  overviewError: undefined as unknown,
  match: {
    id: 'match-001',
    status: 'new',
    created_at: '2026-10-09T12:00:00Z',
    updated_at: '2026-10-09T12:00:00Z',
    notes: null,
    company: {
      name: 'Example Company',
      domain: 'example.com',
      business_sector: ['Software'],
      country: 'US',
      company_scale: 'small',
      company_status: 'active',
    },
  } as Match,
  matchPending: false,
  matchError: false,
  matchApiError: undefined as unknown,
  signalPage: { items: [], limit: 50, offset: 0, has_more: false },
  signalPending: false,
  signalError: false,
  signalApiError: undefined as unknown,
}));

vi.mock('@/features/matches/composables/useMatches', () => ({
  useMatches: () => ({
    status: { value: state.status },
    offset: { value: state.offset },
    pageSize: 50,
    setStatus: state.setStatus,
    setOffset: state.setOffset,
    previousPage: state.previousPage,
    nextPage: state.nextPage,
    matches: {
      data: { value: state.page },
      isPending: { value: state.listPending },
      isError: { value: state.listErrorFlag },
      isFetching: { value: false },
      error: { value: state.listError },
      refetch: state.retryMatches,
    },
  }),
}));
vi.mock('@/features/matches/composables/useMatchesOverview', () => ({
  useMatchesOverview: () => ({
    overview: {
      data: { value: state.overview },
      isPending: { value: false },
      isError: { value: state.overviewErrorFlag },
      isFetching: { value: false },
      error: { value: state.overviewError },
      refetch: state.retryOverview,
    },
  }),
}));
vi.mock('@/features/matches/composables/useMatch', () => ({
  useMatch: () => ({
    query: {
      data: { value: state.match },
      isPending: { value: state.matchPending },
      isError: { value: state.matchError },
      isFetching: { value: false },
      error: { value: state.matchApiError },
      refetch: vi.fn(),
    },
  }),
}));
vi.mock('@/features/matches/composables/useMatchSignals', () => ({
  useMatchSignals: () => ({
    signals: {
      data: { value: state.signalPage },
      isPending: { value: state.signalPending },
      isError: { value: state.signalError },
      isFetching: { value: false },
      error: { value: state.signalApiError },
      refetch: vi.fn(),
    },
    offset: { value: 0 },
    pageSize: 50,
    previousPage: vi.fn(),
    nextPage: vi.fn(),
  }),
}));
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { id: 'match-001' } }),
}));

const global = {
  plugins: [PrimeVue],
  stubs: { RouterLink: { template: '<a><slot /></a>' }, Select: { template: '<div />' } },
};

beforeEach(() => {
  state.status = undefined;
  state.offset = 0;
  state.page = { items: [], limit: 50, offset: 0, has_more: false };
  state.overview = { has_matches: false, has_active_strategies: true, latest_evaluation: null };
  state.setStatus.mockReset();
  state.setOffset.mockReset();
  state.previousPage.mockReset();
  state.nextPage.mockReset();
  state.retryMatches.mockReset();
  state.listPending = false;
  state.listErrorFlag = false;
  state.listError = undefined;
  state.retryOverview.mockReset();
  state.overviewErrorFlag = false;
  state.overviewError = undefined;
  state.match = {
    id: 'match-001',
    status: 'new',
    created_at: '2026-10-09T12:00:00Z',
    updated_at: '2026-10-09T12:00:00Z',
    notes: null,
    company: {
      name: 'Example Company',
      domain: 'example.com',
      business_sector: ['Software'],
      country: 'US',
      company_scale: 'small',
      company_status: 'active',
    },
  };
  state.matchPending = false;
  state.matchError = false;
  state.matchApiError = undefined;
  state.signalPage = { items: [], limit: 50, offset: 0, has_more: false };
  state.signalPending = false;
  state.signalError = false;
  state.signalApiError = undefined;
});

describe('matches workspace', () => {
  it('keeps overall empty context separate from status-filter and out-of-range empty pages', async () => {
    state.status = 'contacted';
    const filtered = mount(MatchesPage, { global });
    expect(filtered.text()).toContain('No matches are on this page');
    expect(filtered.text()).not.toContain('No managed evaluation is recorded');
    await filtered.get('button[aria-label="Clear filter"]').trigger('click');
    expect(state.setStatus).toHaveBeenCalledWith(undefined);

    state.status = undefined;
    state.offset = 50;
    state.overview = { ...overviewWithoutMatches, has_matches: true };
    const outOfRange = mount(MatchesPage, { global });
    expect(outOfRange.text()).toContain('This page has no matches');
    expect(outOfRange.text()).not.toContain('You have no matches yet');
    await outOfRange.get('button[aria-label="First page"]').trigger('click');
    expect(state.setOffset).toHaveBeenCalledWith(0);
  });

  it('maps an overall empty account from overview evidence without claiming a legacy run never happened', () => {
    const noStrategy = mount(MatchOverviewEmptyState, {
      props: { overview: { ...overviewWithoutMatches, has_active_strategies: false } },
      global,
    });
    expect(noStrategy.text()).toContain('Add an active discovery strategy');
    const noRecordedRun = mount(MatchOverviewEmptyState, {
      props: { overview: overviewWithoutMatches },
      global,
    });
    expect(noRecordedRun.text()).toContain('No managed evaluation is recorded');
    expect(noRecordedRun.text()).not.toContain('never ran');

    const evaluation = {
      requested_at: '2026-10-09T12:00:00Z',
      started_at: '2026-10-09T12:00:01Z',
      finished_at: '2026-10-09T12:01:00Z',
      cutoff: '2026-09-09T12:00:00Z',
      as_of: '2026-10-09T12:00:00Z',
      strategies_evaluated: 1,
      strategies_skipped: 0,
      created_matches_count: 0,
      existing_matches_skipped_count: 0,
      tracking_stale: false,
    } as const;
    const succeededZero = mount(MatchOverviewEmptyState, {
      props: {
        overview: {
          ...overviewWithoutMatches,
          latest_evaluation: { ...evaluation, state: 'succeeded' },
        },
      },
    });
    expect(succeededZero.text()).toContain('latest completed evaluation created no new matches');
    for (const unknownState of [
      { ...evaluation, state: 'running' as const },
      { ...evaluation, state: 'pending' as const },
      { ...evaluation, state: 'failed' as const },
      { ...evaluation, state: 'commit_outcome_unknown' as const },
      { ...evaluation, state: 'succeeded' as const, tracking_stale: true },
    ]) {
      const unknown = mount(MatchOverviewEmptyState, {
        props: {
          overview: { ...overviewWithoutMatches, latest_evaluation: unknownState },
        },
      });
      expect(unknown.text()).toContain('Evaluation status is pending or unavailable');
    }
  });

  it('announces the initial list load and does not offer a retry for a terminal not-found response', () => {
    state.page = undefined as unknown as typeof state.page;
    state.listPending = true;
    const loading = mount(MatchesPage, { global });
    expect(loading.text()).toContain('Loading your matches');

    state.listPending = false;
    state.listErrorFlag = true;
    state.listError = new ApiError(404, 'not_found', 'Not found');
    const failed = mount(MatchesPage, { global });
    expect(failed.text()).toContain('Your matches could not be loaded.');
    expect(failed.findAll('button').some((button) => button.text() === 'Retry matches')).toBe(
      false,
    );
  });

  it('shows stored status and current context, with signals independently paged', () => {
    const wrapper = mount(MatchDetailPage, { global });
    expect(wrapper.text()).toContain('Example Company');
    expect(wrapper.text()).toContain('new');
    expect(wrapper.text()).toContain('Current company context');
    expect(wrapper.text()).toContain('They do not explain why this match was created.');
    expect(wrapper.text()).toContain('Current company signals');
    expect(wrapper.text()).toContain('No current company signals are available.');
    expect(
      wrapper
        .findAll('a[target="_blank"]')
        .every((link) => link.attributes('rel') === 'noopener noreferrer'),
    ).toBe(true);
  });

  it('keeps existing matches visible when the latest evaluation created none', () => {
    state.page = { items: [companyMatch], limit: 20, offset: 0, has_more: false };
    state.overview = {
      ...overviewWithoutMatches,
      has_matches: true,
      latest_evaluation: {
        state: 'succeeded',
        requested_at: '2026-10-09T12:00:00Z',
        started_at: '2026-10-09T12:00:01Z',
        finished_at: '2026-10-09T12:01:00Z',
        cutoff: '2026-09-09T12:00:00Z',
        as_of: '2026-10-09T12:00:00Z',
        strategies_evaluated: 1,
        strategies_skipped: 0,
        created_matches_count: 0,
        existing_matches_skipped_count: 0,
        tracking_stale: false,
      },
    };
    const wrapper = mount(MatchesPage, { global });
    expect(wrapper.text()).toContain('Example Company');
    expect(wrapper.text()).not.toContain('You have no matches yet');
    expect(wrapper.find('[data-testid="match-row"]').exists()).toBe(true);
  });

  it('offers recovery only for recoverable read errors and keeps independent list data visible', () => {
    state.page = { items: [companyMatch], limit: 50, offset: 0, has_more: false };
    state.overviewErrorFlag = true;
    state.overviewError = new Error('Network unavailable');
    const overviewFailure = mount(MatchesPage, { global });
    expect(overviewFailure.text()).toContain('Evaluation context could not be loaded');
    expect(overviewFailure.text()).toContain('Example Company');
    expect(
      overviewFailure.findAll('button').some((button) => button.text() === 'Retry overview'),
    ).toBe(true);

    state.page = undefined as unknown as typeof state.page;
    state.overviewErrorFlag = false;
    state.listErrorFlag = true;
    state.listError = new ApiError(404, 'not_found', 'Not found');
    const notFound = mount(MatchesPage, { global });
    expect(notFound.text()).toContain('Your matches could not be loaded.');
    expect(notFound.findAll('button').some((button) => button.text() === 'Retry matches')).toBe(
      false,
    );
  });

  it('shows detail and company fields if the independent signals request fails', () => {
    state.signalPage = undefined as unknown as typeof state.signalPage;
    state.signalError = true;
    state.signalApiError = new ApiError(404, 'not_found', 'Not found');
    const wrapper = mount(MatchDetailPage, { global });
    expect(wrapper.text()).toContain('Example Company');
    expect(wrapper.text()).toContain('Current company context');
    expect(wrapper.text()).toContain('Current company signals could not be loaded.');
    expect(wrapper.findAll('button').some((button) => button.text() === 'Retry signals')).toBe(
      false,
    );
  });
});
