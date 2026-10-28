import { beforeEach, expect, it, vi } from 'vitest';
import { configureApiClient } from '../../src/api/client';
import { generateRecommendations } from '../../src/features/recommendations/api/generateRecommendations';
import { getRecommendationBatch } from '../../src/features/recommendations/api/getRecommendationBatch';
import { getLatestRecommendations } from '../../src/features/recommendations/api/getLatestRecommendations';
import { saveRecommendationFeedback } from '../../src/features/recommendations/api/saveRecommendationFeedback';
beforeEach(() => {
  configureApiClient({ getCsrfToken: () => 'proof' });
  vi.restoreAllMocks();
});
it('generates and resumes a strategy batch through the session API', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  await generateRecommendations('strategy-1');
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/recommendations');
  expect(fetcher.mock.calls[0]?.[1]?.body).toBe(
    JSON.stringify({ strategy_id: 'strategy-1', limit: 10 }),
  );
  expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get('X-CSRF-Token')).toBe('proof');
  await getLatestRecommendations('strategy-1');
  expect(fetcher.mock.calls[1]?.[0]).toBe('/api/v1/recommendations/latest?strategy_id=strategy-1');
});
it('sends detailed feedback with both batch and recommendation identity', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  const draft = {
    recommendation_id: 'company-1',
    usefulness: 'not_useful' as const,
    reasons: ['customer_not_buyer' as const],
    correction: 'A supplier',
    next_step: 'skip' as const,
    outcome: 'not_relevant' as const,
    notes: 'Wrong buying role',
  };
  await saveRecommendationFeedback('batch-1', draft);
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/recommendations/batch-1/feedback');
  expect(fetcher.mock.calls[0]?.[1]?.body).toBe(JSON.stringify(draft));
});

it('loads the exact saved batch through the session API', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  const controller = new AbortController();
  await getRecommendationBatch('saved-batch', controller.signal);
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/recommendations/saved-batch');
  expect(fetcher.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
});
