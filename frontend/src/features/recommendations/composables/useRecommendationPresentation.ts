import { computed, reactive, watch } from 'vue';
import { ApiError } from '../../../api/apiError';
import { createRequestId } from '../../../shared/requests/createRequestId';
import { prepareRecommendationOffer } from '../api/prepareRecommendationOffer';
import { confirmRecommendationOffer } from '../api/confirmRecommendationOffer';
import { isNewAppOffer, type OfferPresentation } from '../models/offerPresentation';
import type { RecommendationView } from '../models/prospecting';

const registry = new Map<string, Map<string, OfferPresentation>>();

export function useRecommendationPresentation(props: {
  readonly identity: string;
  readonly recommendation: RecommendationView;
  readonly newlySelected: boolean;
  readonly historical: boolean;
}) {
  watch(
    () => props.identity,
    (_, previous) => registry.delete(previous),
  );
  const state = computed(() => {
    if (props.historical) return null;
    let entries = registry.get(props.identity);
    const unresolved =
      entries &&
      [...entries.values()].find(
        (entry) =>
          entry.snapshot.id === props.recommendation.id &&
          ['preparing', 'rendered', 'confirming', 'uncertain'].includes(entry.status),
      );
    if (unresolved) return unresolved;
    const revisionId = props.recommendation.assessment?.id;
    if (!revisionId || !isNewAppOffer(props.recommendation, props.newlySelected)) return null;
    if (!entries) {
      entries = new Map();
      registry.set(props.identity, entries);
    }
    const key = `${props.recommendation.id}:${revisionId}`;
    let value = entries.get(key);
    if (!value) {
      value = reactive({
        snapshot: props.recommendation,
        requestKey: createRequestId(),
        status: 'idle',
        preparation: null,
        error: '',
      } satisfies OfferPresentation);
      entries.set(key, value);
    }
    return value;
  });

  function fail(value: OfferPresentation, error: unknown): void {
    const known = error instanceof ApiError && error.status < 500;
    value.status = known ? 'blocked' : 'uncertain';
    value.error = known
      ? 'This recommendation could not be offered again. You can still read its saved assessment.'
      : 'Presentation could not be confirmed. Retry to check the same request.';
  }
  async function prepare(): Promise<void> {
    const value = state.value;
    if (!value || !['idle', 'uncertain'].includes(value.status) || value.preparation) return;
    const revisionId = value.snapshot.assessment?.id;
    if (!revisionId) return;
    const identity = props.identity;
    value.status = 'preparing';
    value.error = '';
    try {
      const prepared = await prepareRecommendationOffer(value.snapshot.id, {
        assessment_revision_id: revisionId,
        request_key: value.requestKey,
      });
      if (identity !== props.identity) return;
      if (
        prepared.recommendation_id !== value.snapshot.id ||
        prepared.assessment_revision_id !== revisionId
      )
        throw new Error('The prepared assessment does not match.');
      value.preparation = prepared;
      if (prepared.status === 'confirmed') value.status = 'confirmed';
      else if (prepared.status === 'preparing' && prepared.claim_token) value.status = 'rendered';
      else {
        value.status = 'blocked';
        value.error = 'This offer is no longer available. Its assessment remains readable.';
      }
    } catch (error) {
      if (identity === props.identity) fail(value, error);
    }
  }
  async function confirm(): Promise<boolean> {
    const value = state.value;
    if (!value?.preparation?.claim_token || !['rendered', 'uncertain'].includes(value.status))
      return false;
    const identity = props.identity;
    value.status = 'confirming';
    value.error = '';
    try {
      await confirmRecommendationOffer(value.preparation.offer_cycle_id, {
        claim_token: value.preparation.claim_token,
      });
      if (identity !== props.identity) return false;
      value.status = 'confirmed';
      return true;
    } catch (error) {
      if (identity === props.identity) fail(value, error);
      return false;
    }
  }
  return { state, prepare, confirm };
}
