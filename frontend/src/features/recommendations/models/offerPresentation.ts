import type { components } from '../../../api/generated/schema';
import type { RecommendationView } from './prospecting';

export interface OfferPresentation {
  snapshot: RecommendationView;
  requestKey: string;
  status: 'idle' | 'preparing' | 'rendered' | 'confirming' | 'confirmed' | 'uncertain' | 'blocked';
  preparation: components['schemas']['PreparedRecommendationOfferResponse'] | null;
  error: string;
}

export function isNewAppOffer(item: RecommendationView): boolean {
  return (
    item.status === 'open' &&
    Boolean(item.assessment) &&
    item.assessment?.id === item.current_revision_id &&
    item.evidence_state === 'current' &&
    !item.selection_blockers.length &&
    !item.assessment_presented_at
  );
}
