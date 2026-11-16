import { expect, it } from 'vitest';
import {
  createRecommendationCommandDraft,
  hasRecommendationFeedbackDraft,
  resetRecommendationDecisionDraft,
} from '../../src/features/recommendations/models/recommendationCommandDraft';
import type { RecommendationView } from '../../src/features/recommendations/models/prospecting';

it('does not recover unsent feedback even when a separate decision captured the recommendation', () => {
  const draft = createRecommendationCommandDraft('rec-1');
  draft.snapshot = { id: 'rec-1' } as RecommendationView;
  Object.assign(draft.feedback, {
    open: true,
    usefulness: 'not_useful',
    notes: 'Temporary notes.',
    status: 'error',
  });
  expect(hasRecommendationFeedbackDraft(draft.feedback)).toBe(false);
  resetRecommendationDecisionDraft(draft);
  expect(draft.snapshot).toBeNull();
});

it.each(['pending', 'uncertain'] as const)('recovers only the submitted %s request', (status) => {
  const draft = createRecommendationCommandDraft('rec-1');
  const snapshot = { id: 'rec-1' } as RecommendationView;
  draft.snapshot = snapshot;
  draft.feedback.status = status;
  draft.feedback.intent = {
    identity: 'identity-1',
    recommendationId: 'rec-1',
    request: {
      assessment_revision_id: 'revision-1',
      request_key: 'request-1',
      feedback: {
        usefulness: 'useful',
        reasons: [],
        outcome: 'unknown',
        next_step: 'none',
        correction: '',
        notes: '',
      },
    },
  };
  expect(hasRecommendationFeedbackDraft(draft.feedback)).toBe(true);
  resetRecommendationDecisionDraft(draft);
  expect(draft.snapshot).toBe(snapshot);
});
