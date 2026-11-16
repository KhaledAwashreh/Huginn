import type { components } from '../../../api/generated/schema';

export type RecommendationView = components['schemas']['RecommendationResponse'];
export type RecommendationPage = components['schemas']['PageResponse_RecommendationResponse_'];
export type RecommendationStatusFilter = 'open' | 'converted' | 'rejected' | 'all';
export type SuppressionView = components['schemas']['SuppressionResponse'];
export type SuppressionPage = components['schemas']['PageResponse_SuppressionResponse_'];
export type RecommendationPreferences =
  components['schemas']['BusinessRecommendationPreferencesResponse'];
export type RecommendationGenerationResult =
  components['schemas']['GenerateRecommendationsResponse'];
