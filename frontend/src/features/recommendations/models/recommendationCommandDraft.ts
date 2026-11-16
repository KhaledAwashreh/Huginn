import type { components } from '../../../api/generated/schema';
import type { RecommendationView } from './prospecting';

export interface RecommendationFeedbackIntent {
  identity: string;
  recommendationId: string;
  request: components['schemas']['RecordRecommendationFeedbackRequest'];
}

export interface RecommendationFeedbackDraft {
  open: boolean;
  usefulness: components['schemas']['RecommendationQualityFeedbackRequest']['usefulness'];
  reasons: components['schemas']['FeedbackReason'][];
  outcome: components['schemas']['RecommendationQualityFeedbackRequest']['outcome'];
  next_step: components['schemas']['RecommendationQualityFeedbackRequest']['next_step'];
  correction: string;
  notes: string;
  status: 'idle' | 'pending' | 'uncertain' | 'error';
  error: string;
  intent: RecommendationFeedbackIntent | null;
}

export type RecommendationCommandIntent =
  | {
      identity: string;
      recommendationId: string;
      kind: 'saved';
      request: components['schemas']['SaveRecommendationRequest'];
    }
  | {
      identity: string;
      recommendationId: string;
      kind: 'not_relevant';
      request: components['schemas']['MarkRecommendationNotRelevantRequest'];
    }
  | {
      identity: string;
      recommendationId: string;
      kind: 'later';
      request: components['schemas']['LaterRecommendationRequest'];
    };

export interface RecommendationCommandDraft {
  recommendationId: string;
  snapshot: RecommendationView | null;
  reason: string;
  pauseChoice: components['schemas']['LaterRecommendationRequest']['pause_choice'];
  laterConfirmationOpen: boolean;
  status: 'idle' | 'pending' | 'uncertain' | 'stale' | 'editing';
  error: string;
  intent: RecommendationCommandIntent | null;
  feedback: RecommendationFeedbackDraft;
}

export interface RecommendationCommandRecovery {
  recommendationId: string;
  snapshot: RecommendationView;
  draft: RecommendationCommandDraft;
  decisionDraft: boolean;
  feedbackDraft: boolean;
}

export function createRecommendationCommandDraft(
  recommendationId: string,
): RecommendationCommandDraft {
  return {
    recommendationId,
    snapshot: null,
    reason: '',
    pauseChoice: 'x1',
    laterConfirmationOpen: false,
    status: 'idle',
    error: '',
    intent: null,
    feedback: {
      open: false,
      usefulness: 'unsure',
      reasons: [],
      outcome: 'unknown',
      next_step: 'none',
      correction: '',
      notes: '',
      status: 'idle',
      error: '',
      intent: null,
    },
  };
}

export function hasRecommendationFeedbackDraft(draft: RecommendationFeedbackDraft): boolean {
  return draft.intent !== null && (draft.status === 'pending' || draft.status === 'uncertain');
}

export function resetRecommendationDecisionDraft(draft: RecommendationCommandDraft): void {
  const feedback = draft.feedback;
  const snapshot = hasRecommendationFeedbackDraft(feedback) ? draft.snapshot : null;
  Object.assign(draft, createRecommendationCommandDraft(draft.recommendationId), {
    feedback,
    snapshot,
  });
}
