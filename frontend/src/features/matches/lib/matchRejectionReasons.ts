import type { FeedbackReason } from '../../recommendations/models/recommendationFeedback';

export const MATCH_REJECTION_REASONS: { value: FeedbackReason; label: string }[] = [
  { value: 'company_fit', label: 'Not the kind of company I work with' },
  { value: 'service_fit', label: 'They would not need my services' },
  { value: 'customer_not_buyer', label: 'They would not be the buyer' },
  { value: 'geography', label: 'Wrong location' },
  { value: 'timing', label: 'Bad timing' },
  { value: 'evidence_wrong', label: 'The information about them is wrong' },
  { value: 'already_known', label: 'I already know them' },
  { value: 'other', label: 'Something else' },
];

export function matchRejectionReasonLabel(reason: FeedbackReason): string {
  return MATCH_REJECTION_REASONS.find((option) => option.value === reason)?.label ?? reason;
}
