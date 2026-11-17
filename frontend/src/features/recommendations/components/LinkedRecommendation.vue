<script setup lang="ts">
import { computed, watch } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import Button from 'primevue/button';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import { getRecommendation } from '../api/getRecommendation';
import type { RecommendationPreferences } from '../models/prospecting';
import type { RecommendationCommandDraft } from '../models/recommendationCommandDraft';
import RecommendationEvidence from './RecommendationEvidence.vue';
import RecommendationCommandActions from './RecommendationCommandActions.vue';
import RecommendationQualityFeedback from './RecommendationQualityFeedback.vue';

const props = defineProps<{
  recommendationId: string;
  assessmentRevisionId: string;
  identity: string;
  draftState: RecommendationCommandDraft;
  preferences: RecommendationPreferences | null;
  preferencesLoading: boolean;
  preferencesFailed: boolean;
  refreshPreferences: () => Promise<RecommendationPreferences>;
}>();
const emit = defineEmits<{
  completed: [event: { kind: string; message: string }];
  available: [value: boolean];
}>();
const detail = useQuery({
  queryKey: computed(() => [
    'prospecting',
    props.identity,
    'recommendations',
    'linked',
    props.recommendationId,
    props.assessmentRevisionId,
  ]),
  queryFn: async ({ signal }) => {
    const result = await getRecommendation(
      props.recommendationId,
      signal,
      props.assessmentRevisionId,
    );
    if (
      result.id !== props.recommendationId ||
      result.assessment?.id !== props.assessmentRevisionId
    )
      throw new Error('The linked assessment is unavailable.');
    return result;
  },
});
watch(
  () => Boolean(detail.data.value && !detail.isError.value),
  (available) => emit('available', available),
  { immediate: true },
);
</script>

<template>
  <section aria-label="Recommendation from your email">
    <h2>Recommendation from your email</h2>
    <p>This is the assessment included in your email. Current company details appear separately.</p>
    <LoadingState v-if="detail.isPending.value" message="Loading the linked assessment…" />
    <ErrorState
      v-else-if="detail.isError.value"
      message="The linked assessment could not be loaded."
    >
      <Button label="Retry linked assessment" @click="detail.refetch()" />
    </ErrorState>
    <template v-else-if="detail.data.value">
      <RecommendationEvidence :recommendation="detail.data.value" />
      <RecommendationCommandActions
        v-if="detail.data.value.status === 'open'"
        :recommendation="detail.data.value"
        :identity="identity"
        :draft-state="draftState"
        :preferences="preferences"
        :preferences-loading="preferencesLoading"
        :preferences-failed="preferencesFailed"
        :refresh-preferences="refreshPreferences"
        @completed="$emit('completed', $event)"
      />
      <RecommendationQualityFeedback
        v-if="draftState.laterConfirmationOpen || draftState.feedback.intent"
        :recommendation="detail.data.value"
        :identity="identity"
        :draft-state="draftState"
      />
    </template>
  </section>
</template>
