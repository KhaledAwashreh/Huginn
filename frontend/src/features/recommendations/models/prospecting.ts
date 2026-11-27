import type { components, operations } from '../../../api/generated/schema';

export type RecommendationView = components['schemas']['RecommendationResponse'];
export type RecommendationPage = components['schemas']['PageResponse_RecommendationResponse_'];
type RecommendationListQuery = NonNullable<
  operations['list_recommendations_api_v1_recommendations_get']['parameters']['query']
>;
export type RecommendationStatusFilter = NonNullable<RecommendationListQuery['status']>;
export type SuppressionView = components['schemas']['SuppressionResponse'];
export type SuppressionPage = components['schemas']['PageResponse_SuppressionResponse_'];
export type RecommendationPreferences =
  components['schemas']['BusinessRecommendationPreferencesResponse'];
export type RecommendationGenerationResult =
  components['schemas']['GenerateRecommendationsResponse'];
