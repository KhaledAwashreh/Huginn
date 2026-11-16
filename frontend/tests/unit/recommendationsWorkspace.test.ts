import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, ref } from 'vue';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { useRecommendationWorkspace } from '../../src/features/recommendations/composables/useRecommendationWorkspace';
import type {
  RecommendationPage,
  RecommendationView,
} from '../../src/features/recommendations/models/prospecting';

const mocks = vi.hoisted(() => ({
  session: { value: null as unknown },
  list: vi.fn(),
  suppressions: vi.fn(),
  preferences: vi.fn(),
  strategies: vi.fn(),
  generate: vi.fn(),
}));
vi.mock('../../src/features/session/composables/useSession', () => ({
  useSession: () => ({ context: mocks.session }),
}));
vi.mock('../../src/features/recommendations/api/listRecommendations', () => ({
  listRecommendations: mocks.list,
}));
vi.mock('../../src/features/recommendations/api/listSuppressions', () => ({
  listSuppressions: mocks.suppressions,
}));
vi.mock('../../src/features/recommendations/api/getBusinessRecommendationPreferences', () => ({
  getBusinessRecommendationPreferences: mocks.preferences,
}));
vi.mock(
  '../../src/features/configuration/discovery-strategies/api/listDiscoveryStrategies',
  () => ({
    listDiscoveryStrategies: mocks.strategies,
  }),
);
vi.mock('../../src/features/recommendations/api/generateRecommendations', () => ({
  generateRecommendations: mocks.generate,
}));

function emptyPage(offset = 0): RecommendationPage {
  return { items: [], offset, limit: 25, has_more: false };
}
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let workspace!: ReturnType<typeof useRecommendationWorkspace>;
  mount(
    defineComponent({
      setup() {
        workspace = useRecommendationWorkspace();
        return () => null;
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  );
  return { client, workspace };
}
beforeEach(() => {
  vi.resetAllMocks();
  mocks.session = ref({ account_id: 'account-1', user_id: 'user-1', csrf_token: 'csrf-1' });
  mocks.list.mockImplementation(async ({ offset }: { offset: number }) => emptyPage(offset));
  mocks.suppressions.mockResolvedValue(emptyPage());
  mocks.preferences.mockResolvedValue({
    repeat_interval_days: 30,
    updated_at: '2026-11-14T10:00:00Z',
  });
  mocks.strategies.mockResolvedValue({ items: [], has_more: false, offset: 0, limit: 100 });
});

it('waits for a strategy and isolates rows and requests when switching strategies', async () => {
  const { workspace } = setup();
  await flushPromises();
  expect(mocks.list).not.toHaveBeenCalled();
  workspace.strategyId.value = 'strategy-1';
  await flushPromises();
  workspace.setOffset(50);
  await flushPromises();
  workspace.strategyId.value = 'strategy-2';
  await flushPromises();
  expect(workspace.offset.value).toBe(0);
  expect(mocks.list).toHaveBeenLastCalledWith(
    { strategyId: 'strategy-2', status: 'open', search: '', offset: 0, limit: 25 },
    expect.any(AbortSignal),
  );
  expect(
    mocks.list.mock.calls.some(
      ([options]) => options.strategyId === 'strategy-2' && options.offset === 50,
    ),
  ).toBe(false);
  workspace.strategyId.value = '';
  await flushPromises();
  expect(workspace.recommendations.data.value).toBeUndefined();
});

it('hides the previous strategy rows while its replacement request is pending', async () => {
  let finishRequest!: (page: RecommendationPage) => void;
  mocks.list.mockResolvedValueOnce({ ...emptyPage(), items: [{ id: 'strategy-one-rec' }] });
  const { workspace } = setup();
  workspace.strategyId.value = 'strategy-1';
  await flushPromises();
  expect(workspace.recommendations.data.value?.items[0]?.id).toBe('strategy-one-rec');
  mocks.list.mockImplementationOnce(
    () =>
      new Promise<RecommendationPage>((resolve) => {
        finishRequest = resolve;
      }),
  );
  workspace.strategyId.value = 'strategy-2';
  await flushPromises();
  expect(workspace.recommendations.data.value).toBeUndefined();
  finishRequest(emptyPage());
  await flushPromises();
});

it('searches and filters on the server and resets pagination on each query change', async () => {
  const { workspace } = setup();
  await flushPromises();
  workspace.strategyId.value = 'strategy-1';
  await flushPromises();
  workspace.setOffset(50);
  await flushPromises();
  workspace.search.value = 'northstar.example';
  await flushPromises();
  workspace.status.value = 'converted';
  await flushPromises();
  expect(workspace.offset.value).toBe(0);
  expect(mocks.list).toHaveBeenLastCalledWith(
    {
      strategyId: 'strategy-1',
      status: 'converted',
      search: 'northstar.example',
      offset: 0,
      limit: 25,
    },
    expect.any(AbortSignal),
  );
});

it('posts a generation request then refreshes the canonical list without inserting returned references', async () => {
  const { workspace, client } = setup();
  await flushPromises();
  const generated = {
    run_id: 'run-1',
    references: [{ recommendation_id: 'rec-1', revision_id: 'rev-1', recommendation_version: 2 }],
  };
  mocks.generate.mockResolvedValue(generated);
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const setData = vi.spyOn(client, 'setQueryData');
  await workspace.generate('strategy-1');
  expect(mocks.generate).toHaveBeenCalledWith('strategy-1', 10);
  expect(invalidate).toHaveBeenCalledWith({ queryKey: workspace.recommendationsKey.value });
  expect(setData).not.toHaveBeenCalled();
  expect(workspace.generationResult.value).toEqual(generated);
});

it('resets server rows and search state when the authenticated identity changes', async () => {
  mocks.list.mockResolvedValueOnce({ ...emptyPage(), items: [{ id: 'private-rec' }] });
  const { workspace, client } = setup();
  workspace.strategyId.value = 'strategy-1';
  await flushPromises();
  workspace.search.value = 'private';
  await flushPromises();
  mocks.session.value = { account_id: 'account-2', user_id: 'user-2', csrf_token: 'csrf-2' };
  await flushPromises();
  expect(workspace.search.value).toBe('');
  expect(workspace.strategyId.value).toBe('');
  expect(client.getQueryData(workspace.recommendationsKey.value)).not.toEqual(
    expect.objectContaining({ items: [{ id: 'private-rec' }] }),
  );
});

it('retains a recommendation action draft across row removal and pagination, but scopes it to identity', async () => {
  const { workspace } = setup();
  await flushPromises();
  const draft = workspace.commandDraftFor('rec-1');
  draft.reason = 'The purchasing role is not verified.';
  draft.snapshot = { id: 'rec-1', status: 'open' } as RecommendationView;
  draft.pauseChoice = 'x3';
  draft.status = 'uncertain';
  draft.feedback.notes = 'Retain this report draft too.';
  draft.feedback.status = 'uncertain';
  draft.feedback.intent = {
    identity: workspace.identity.value,
    recommendationId: 'rec-1',
    request: {
      assessment_revision_id: 'revision-1',
      request_key: 'fixed-feedback-key',
      feedback: {
        usefulness: 'not_useful',
        reasons: ['evidence_wrong'],
        outcome: 'unknown',
        next_step: 'none',
        correction: '',
        notes: 'Retain this report draft too.',
      },
    },
  };
  draft.intent = {
    identity: workspace.identity.value,
    recommendationId: 'rec-1',
    kind: 'not_relevant',
    request: {
      assessment_revision_id: 'revision-1',
      expected_recommendation_version: 4,
      reason: 'The purchasing role is not verified.',
      request_key: 'fixed-request-key',
    },
  };

  workspace.setOffset(25);
  await flushPromises();
  expect(workspace.commandDraftFor('rec-1')).toMatchObject({
    reason: 'The purchasing role is not verified.',
    pauseChoice: 'x3',
    status: 'uncertain',
    intent: { recommendationId: 'rec-1', request: { request_key: 'fixed-request-key' } },
    feedback: {
      notes: 'Retain this report draft too.',
      status: 'uncertain',
      intent: { request: { request_key: 'fixed-feedback-key' } },
    },
  });
  expect(workspace.commandRecoveries.value).toMatchObject([
    { recommendationId: 'rec-1', snapshot: { id: 'rec-1' }, decisionDraft: true },
  ]);

  const remounted = setup().workspace;
  expect(remounted.commandDraftFor('rec-1')).toMatchObject({
    reason: 'The purchasing role is not verified.',
    intent: { request: { request_key: 'fixed-request-key' } },
  });

  mocks.session.value = { account_id: 'account-2', user_id: 'user-2', csrf_token: 'csrf-2' };
  await flushPromises();
  expect(workspace.commandDraftFor('rec-1')).not.toMatchObject({
    reason: 'The purchasing role is not verified.',
    intent: { request: { request_key: 'fixed-request-key' } },
  });
  expect(workspace.commandDraftFor('rec-1')).toMatchObject({
    reason: '',
    pauseChoice: 'x1',
    status: 'idle',
    intent: null,
    feedback: { notes: '', status: 'idle', intent: null },
  });
  expect(workspace.commandRecoveries.value).toEqual([]);
});

it('does not read suppressions until the user opens their manager', async () => {
  const { workspace } = setup();
  await flushPromises();
  expect(mocks.suppressions).not.toHaveBeenCalled();
  workspace.suppressionsVisible.value = true;
  await flushPromises();
  expect(mocks.suppressions).toHaveBeenCalledWith(
    { search: '', offset: 0, limit: 25 },
    expect.any(AbortSignal),
  );
});
