import { computed, ref, watch } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { listDiscoveryStrategies } from '../../configuration/discovery-strategies/api/listDiscoveryStrategies';
import { getLatestRecommendations } from '../api/getLatestRecommendations';
import { generateRecommendations } from '../api/generateRecommendations';
import { listRecommendationFeedback } from '../api/listRecommendationFeedback';
import { ApiError } from '../../../api/apiError';
export function useRecommendations() {
  const session = useSession();
  const client = useQueryClient();
  const identity = computed(() =>
    [
      session.context.value?.account_id,
      session.context.value?.user_id,
      session.context.value?.csrf_token,
    ].join(':'),
  );
  const strategyId = ref('');
  const generating = ref(false);
  const generationError = ref('');
  let version = 0;
  watch(identity, () => {
    strategyId.value = '';
    version++;
    generating.value = false;
    generationError.value = '';
  });
  watch(strategyId, () => {
    version++;
    generating.value = false;
    generationError.value = '';
  });
  const strategies = useQuery({
    queryKey: computed(() => ['recommendations', identity.value, 'strategies']),
    enabled: computed(() => Boolean(session.context.value)),
    queryFn: async ({ signal }) => {
      const items = [];
      let offset = 0;
      let more = true;
      while (more) {
        const page = await listDiscoveryStrategies(offset, 100, true, signal);
        items.push(...page.items);
        more = page.has_more;
        offset += 100;
      }
      return items;
    },
  });
  const batchKey = computed(() => ['recommendations', identity.value, 'latest', strategyId.value]);
  const batch = useQuery({
    queryKey: batchKey,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    enabled: computed(() => Boolean(session.context.value && strategyId.value)),
    queryFn: async ({ signal }) => {
      try {
        return await getLatestRecommendations(strategyId.value, signal);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
  const feedbackKey = computed(() => [
    'recommendations',
    identity.value,
    'feedback',
    batch.data.value?.id,
  ]);
  const feedback = useQuery({
    queryKey: feedbackKey,
    enabled: computed(() => Boolean(batch.data.value?.id)),
    queryFn: ({ signal }) => {
      const id = batch.data.value?.id;
      if (!id) throw new Error('Choose a recommendation batch.');
      return listRecommendationFeedback(id, signal);
    },
  });
  async function generate() {
    if (!strategyId.value || generating.value) return;
    const started = version;
    const key = [...batchKey.value];
    generating.value = true;
    generationError.value = '';
    try {
      const result = await generateRecommendations(strategyId.value);
      if (started === version) {
        await client.cancelQueries({ queryKey: key });
        if (started === version) client.setQueryData(key, result);
      }
    } catch (error) {
      if (started === version)
        generationError.value =
          error instanceof ApiError && error.status === 403
            ? 'Reload the page before trying again.'
            : error instanceof ApiError && error.status === 422
              ? 'Review your strategy and offering topics before generating recommendations. Use explicit countries for geographic exclusions; region exclusions are not supported.'
              : 'Recommendations could not be generated. Try again.';
    } finally {
      if (started === version) generating.value = false;
    }
  }
  return {
    identity,
    strategyId,
    strategies,
    batch,
    feedback,
    feedbackKey,
    generating,
    generationError,
    generate,
  };
}
