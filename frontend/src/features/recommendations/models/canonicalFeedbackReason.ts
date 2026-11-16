import type { FeedbackReason } from './recommendationFeedback';

const FEEDBACK_REASON_LABELS: Record<FeedbackReason, string> = {
  company_fit: 'Not the kind of company I work with',
  service_fit: 'They would not need my services',
  customer_not_buyer: 'They would not be the buyer',
  geography: 'Wrong location',
  timing: 'Bad timing',
  evidence_wrong: 'The information about them is wrong',
  already_known: 'I already know them',
  other: 'Something else',
};

export function canonicalFeedbackReason(reason: FeedbackReason): string {
  return FEEDBACK_REASON_LABELS[reason] ?? reason;
}
