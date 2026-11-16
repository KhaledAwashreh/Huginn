import { expect, it } from 'vitest';
import { canonicalFeedbackReason } from '@/features/recommendations/models/canonicalFeedbackReason';

it('uses the recommendation workflow labels for feedback reasons', () => {
  expect(canonicalFeedbackReason('company_fit')).toBe('Not the kind of company I work with');
  expect(canonicalFeedbackReason('evidence_wrong')).toBe('The information about them is wrong');
  expect(canonicalFeedbackReason('already_known')).toBe('I already know them');
});
