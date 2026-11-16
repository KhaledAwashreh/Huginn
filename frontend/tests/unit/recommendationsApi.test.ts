import { beforeEach, expect, it, vi } from 'vitest';
import { configureApiClient } from '../../src/api/client';
import { cancelRecommendationPause } from '../../src/features/recommendations/api/cancelRecommendationPause';
import { generateRecommendations } from '../../src/features/recommendations/api/generateRecommendations';
import { getBusinessRecommendationPreferences } from '../../src/features/recommendations/api/getBusinessRecommendationPreferences';
import { getRecommendation } from '../../src/features/recommendations/api/getRecommendation';
import { laterRecommendation } from '../../src/features/recommendations/api/laterRecommendation';
import { listRecommendations } from '../../src/features/recommendations/api/listRecommendations';
import { listSuppressions } from '../../src/features/recommendations/api/listSuppressions';
import { markRecommendationNotRelevant } from '../../src/features/recommendations/api/markRecommendationNotRelevant';
import { reverseRecommendationRejection } from '../../src/features/recommendations/api/reverseRecommendationRejection';
import { recordRecommendationFeedback } from '../../src/features/recommendations/api/recordRecommendationFeedback';
import { saveRecommendation } from '../../src/features/recommendations/api/saveRecommendation';

beforeEach(() => {
  configureApiClient({ getCsrfToken: () => 'proof' });
  vi.restoreAllMocks();
});

it('queries the full server-filtered recommendation page and preserves abort signals', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  const controller = new AbortController();
  await listRecommendations(
    { status: 'open', search: 'northstar.example', offset: 50, limit: 50 },
    controller.signal,
  );
  expect(fetcher.mock.calls[0]?.[0]).toBe(
    '/api/v1/recommendations?offset=50&limit=50&status=open&search=northstar.example',
  );
  expect(fetcher.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
});

it('fetches a recommendation detail without changing the list scope', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  const controller = new AbortController();
  await getRecommendation('rec/one', controller.signal);
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/recommendations/rec%2Fone');
  expect(fetcher.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
});

it('opens the exact historical assessment from an email without requesting a new offer', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}'));
  const controller = new AbortController();
  await getRecommendation('rec/one', controller.signal, 'old/revision');
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0]?.[0]).toBe(
    '/api/v1/recommendations/rec%2Fone?assessment_revision_id=old%2Frevision',
  );
  expect(fetcher.mock.calls[0]?.[1]?.method).toBe('GET');
});

it('loads Business cadence and suppression views through the session-scoped reads', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  await getBusinessRecommendationPreferences();
  await listSuppressions({ search: 'Northstar', offset: 0, limit: 25 });
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
    '/api/v1/me/business/recommendation-preferences',
    '/api/v1/suppressions?offset=0&limit=25&search=Northstar',
  ]);
});

it('saves and rejects the exact shown assessment with stable request data', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  await saveRecommendation('recommendation-1', {
    assessment_revision_id: 'revision-1',
    request_key: 'save-key',
  });
  await markRecommendationNotRelevant('recommendation-1', {
    assessment_revision_id: 'revision-1',
    expected_recommendation_version: 4,
    reason: 'Wrong buyer',
    request_key: 'reject-key',
  });
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/recommendations/recommendation-1/save');
  expect(fetcher.mock.calls[0]?.[1]?.body).toBe(
    JSON.stringify({ assessment_revision_id: 'revision-1', request_key: 'save-key' }),
  );
  expect(fetcher.mock.calls[1]?.[0]).toBe('/api/v1/recommendations/recommendation-1/not-relevant');
  expect(fetcher.mock.calls[1]?.[1]?.body).toBe(
    JSON.stringify({
      assessment_revision_id: 'revision-1',
      expected_recommendation_version: 4,
      reason: 'Wrong buyer',
      request_key: 'reject-key',
    }),
  );
  for (const [, init] of fetcher.mock.calls) {
    expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('proof');
  }
});

it('sends Later cadence, preference snapshot and explicit null expected pause', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  await laterRecommendation('recommendation-2', {
    assessment_revision_id: 'revision-2',
    expected_pause_id: null,
    expected_pause_version: null,
    expected_preference_updated_at: '2026-11-14T10:00:00Z',
    expected_recommendation_version: 2,
    expected_repeat_interval_days: 30,
    pause_choice: 'x3',
    request_key: 'later-key',
  });
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/recommendations/recommendation-2/later');
  expect(fetcher.mock.calls[0]?.[1]?.body).toBe(
    JSON.stringify({
      assessment_revision_id: 'revision-2',
      expected_pause_id: null,
      expected_pause_version: null,
      expected_preference_updated_at: '2026-11-14T10:00:00Z',
      expected_recommendation_version: 2,
      expected_repeat_interval_days: 30,
      pause_choice: 'x3',
      request_key: 'later-key',
    }),
  );
});

it('cancels pauses and reverses rejection by block ID/version', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  const request = { expected_version: 3, request_key: 'clear-key' };
  await cancelRecommendationPause('pause-block', request);
  await reverseRecommendationRejection('rejection-block', request);
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
    '/api/v1/suppressions/pause-block/cancel-pause',
    '/api/v1/suppressions/rejection-block/reverse-rejection',
  ]);
});

it('reports quality against the exact assessment revision through the report-only endpoint', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  await recordRecommendationFeedback('recommendation-3', {
    assessment_revision_id: 'revision-3',
    request_key: 'feedback-key',
    feedback: {
      usefulness: 'not_useful',
      reasons: ['evidence_wrong'],
      outcome: 'unknown',
      next_step: 'none',
      correction: '',
      notes: 'Stored evidence did not match the source.',
    },
  });
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/recommendations/recommendation-3/feedback');
  expect(fetcher.mock.calls[0]?.[1]?.method).toBe('POST');
  expect(fetcher.mock.calls[0]?.[1]?.body).toBe(
    JSON.stringify({
      assessment_revision_id: 'revision-3',
      request_key: 'feedback-key',
      feedback: {
        usefulness: 'not_useful',
        reasons: ['evidence_wrong'],
        outcome: 'unknown',
        next_step: 'none',
        correction: '',
        notes: 'Stored evidence did not match the source.',
      },
    }),
  );
  expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get('X-CSRF-Token')).toBe('proof');
});

it('returns only generation references for the subsequent canonical list refresh', async () => {
  const generated = {
    run_id: 'run-1',
    references: [{ recommendation_id: 'rec-1', revision_id: 'rev-1', recommendation_version: 2 }],
  };
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response(JSON.stringify(generated), { status: 201 }));
  const result = await generateRecommendations('strategy-1', 10);
  expect(result).toEqual(generated);
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/recommendations');
  expect(fetcher.mock.calls[0]?.[1]?.body).toBe(
    JSON.stringify({ strategy_id: 'strategy-1', limit: 10 }),
  );
  expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get('X-CSRF-Token')).toBe('proof');
});
