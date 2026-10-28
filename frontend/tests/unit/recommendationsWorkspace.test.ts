import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, ref } from 'vue';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '../../src/api/apiError';
import { useRecommendations } from '../../src/features/recommendations/composables/useRecommendations';
import type { RecommendationBatch } from '../../src/features/recommendations/models/recommendation';
const mocks = vi.hoisted(() => ({
  session: { value: null as unknown },
  latest: vi.fn(),
  generate: vi.fn(),
  strategies: vi.fn(),
  feedback: vi.fn(),
}));
vi.mock('../../src/features/session/composables/useSession', () => ({
  useSession: () => ({ context: mocks.session }),
}));
vi.mock('../../src/features/recommendations/api/getLatestRecommendations', () => ({
  getLatestRecommendations: mocks.latest,
}));
vi.mock('../../src/features/recommendations/api/generateRecommendations', () => ({
  generateRecommendations: mocks.generate,
}));
vi.mock('../../src/features/recommendations/api/listRecommendationFeedback', () => ({
  listRecommendationFeedback: mocks.feedback,
}));
vi.mock(
  '../../src/features/configuration/discovery-strategies/api/listDiscoveryStrategies',
  () => ({ listDiscoveryStrategies: mocks.strategies }),
);
function batch(id: string, strategy_id: string): RecommendationBatch {
  return {
    id,
    strategy_id,
    created_at: '2026-10-28T00:00:00Z',
    algorithm_version: 'v1',
    assessment_method: 'Research relevance',
    candidate_count: 0,
    retrieval_limit: 10,
    items: [],
  };
}
function setup(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  let workspace!: ReturnType<typeof useRecommendations>;
  mount(
    defineComponent({
      setup() {
        workspace = useRecommendations();
        return () => null;
      },
    }),
    {
      global: {
        plugins: [[VueQueryPlugin, { queryClient: client }]],
      },
    },
  );
  return workspace;
}
beforeEach(() => {
  vi.resetAllMocks();
  mocks.session = ref({ account_id: 'account-1', user_id: 'user-1', csrf_token: 'proof-1' });
  mocks.strategies.mockResolvedValue({
    items: [{ id: 'strategy-1', name: 'One' }],
    has_more: false,
  });
  mocks.feedback.mockResolvedValue([]);
});
it('treats a missing latest batch as empty and resumes another selected strategy', async () => {
  mocks.latest
    .mockRejectedValueOnce(new ApiError(404, 'not_found', 'Missing'))
    .mockResolvedValueOnce(batch('batch-2', 'strategy-2'));
  const workspace = setup();
  workspace.strategyId.value = 'strategy-1';
  await flushPromises();
  expect(workspace.batch.data.value).toBeNull();
  expect(workspace.batch.isError.value).toBe(false);
  workspace.strategyId.value = 'strategy-2';
  await flushPromises();
  expect(workspace.batch.data.value?.id).toBe('batch-2');
});
it('discards a late generation result after strategy selection changes', async () => {
  mocks.latest.mockResolvedValue(null);
  let resolve!: (batch: RecommendationBatch) => void;
  mocks.generate.mockImplementation(
    () =>
      new Promise<RecommendationBatch>((done) => {
        resolve = done;
      }),
  );
  const workspace = setup();
  workspace.strategyId.value = 'strategy-1';
  await flushPromises();
  const pending = workspace.generate();
  workspace.strategyId.value = 'strategy-2';
  await flushPromises();
  resolve(batch('old-batch', 'strategy-1'));
  await pending;
  expect(workspace.batch.data.value).toBeNull();
  expect(workspace.generating.value).toBe(false);
});
it('clears the selection on identity or session proof change', async () => {
  mocks.latest.mockResolvedValue(batch('batch-1', 'strategy-1'));
  const workspace = setup();
  workspace.strategyId.value = 'strategy-1';
  await flushPromises();
  mocks.session.value = { account_id: 'account-2', user_id: 'user-2', csrf_token: 'proof-2' };
  await flushPromises();
  expect(workspace.strategyId.value).toBe('');
  expect(workspace.batch.data.value).toBeUndefined();
});

it('explains rejected strategy settings without discarding the previous assessment', async () => {
  mocks.latest.mockResolvedValue(batch('batch-1', 'strategy-1'));
  mocks.generate.mockRejectedValue(new ApiError(422, 'validation_error', 'Unsafe server details'));
  const workspace = setup();
  workspace.strategyId.value = 'strategy-1';
  await flushPromises();
  await workspace.generate();
  expect(workspace.generationError.value).toContain('offering topics');
  expect(workspace.generationError.value).toContain('explicit countries');
  expect(workspace.generationError.value).not.toContain('Unsafe server details');
  expect(workspace.batch.data.value?.id).toBe('batch-1');
});

it('does not repopulate cleared session cache if identity changes while generation cancels an old read', async () => {
  mocks.latest.mockResolvedValue(null);
  mocks.generate.mockResolvedValue(batch('old-batch', 'strategy-1'));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const workspace = setup(client);
  workspace.strategyId.value = 'strategy-1';
  await flushPromises();
  let release!: () => void;
  vi.spyOn(client, 'cancelQueries').mockImplementation(
    () =>
      new Promise<void>((done) => {
        release = done;
      }),
  );
  const pending = workspace.generate();
  await flushPromises();
  mocks.session.value = { account_id: 'account-2', user_id: 'user-2', csrf_token: 'proof-2' };
  await flushPromises();
  client.clear();
  release();
  await pending;
  expect(
    client.getQueryData(['recommendations', 'account-1:user-1:proof-1', 'latest', 'strategy-1']),
  ).toBeUndefined();
});
