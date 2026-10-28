import { computed, ref, watch, type Ref } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { useSession } from '../../session/composables/useSession';
import { listDiscoveryStrategies } from '../../configuration/discovery-strategies/api/listDiscoveryStrategies';
import { getRecommendationBatch } from '../api/getRecommendationBatch';
import { getLatestRecommendations } from '../api/getLatestRecommendations';
import { generateRecommendations } from '../api/generateRecommendations';
import { listRecommendationFeedback } from '../api/listRecommendationFeedback';
import { ApiError } from '../../../api/apiError';
import { listWeeklyMatches } from '../api/listWeeklyMatches';
export function useRecommendations(
  requestedBatch: Readonly<Ref<string>> = ref(''),
  weekly: Readonly<Ref<boolean>> = ref(false),
) {
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
  const pinnedBatch = ref(requestedBatch.value);
  const historyOffset = ref(0);
  let selectingSavedStrategy = false;
  function setSavedStrategy(value: string) {
    selectingSavedStrategy = true;
    strategyId.value = value;
    selectingSavedStrategy = false;
  }
  const generating = ref(false);
  const generationError = ref('');
  let version = 0;
  watch(identity, () => {
    setSavedStrategy('');
    pinnedBatch.value = requestedBatch.value;
    version++;
    generating.value = false;
    generationError.value = '';
    historyOffset.value = 0;
  });
  watch(
    strategyId,
    () => {
      if (!selectingSavedStrategy) pinnedBatch.value = '';
      version++;
      generating.value = false;
      generationError.value = '';
    },
    { flush: 'sync' },
  );
  watch(requestedBatch, (value) => {
    if (!value && !pinnedBatch.value) return;
    pinnedBatch.value = value;
    setSavedStrategy('');
    version++;
  });
  watch(weekly, () => {
    pinnedBatch.value = requestedBatch.value;
    setSavedStrategy('');
    historyOffset.value = 0;
    version++;
  });
  const weeklyHistory = useQuery({
    queryKey: computed(() => ['recommendations', identity.value, 'weekly', historyOffset.value]),
    enabled: computed(() => Boolean(session.context.value && weekly.value)),
    queryFn: ({ signal }) => listWeeklyMatches(historyOffset.value, signal),
  });
  watch([weeklyHistory.data, requestedBatch], ([value]) => {
    const first = value?.[0];
    if (weekly.value && !pinnedBatch.value && first) pinnedBatch.value = first.id;
  });
  const strategies = useQuery({
    queryKey: computed(() => ['recommendations', identity.value, 'strategies']),
    enabled: computed(() => Boolean(session.context.value && !weekly.value)),
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
  const batchKey = computed(() => [
    'recommendations',
    identity.value,
    pinnedBatch.value ? 'saved' : 'latest',
    pinnedBatch.value || strategyId.value,
  ]);
  const batch = useQuery({
    queryKey: batchKey,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    enabled: computed(() =>
      Boolean(session.context.value && (pinnedBatch.value || (!weekly.value && strategyId.value))),
    ),
    queryFn: async ({ signal }) => {
      if (pinnedBatch.value) return getRecommendationBatch(pinnedBatch.value, signal);
      try {
        return await getLatestRecommendations(strategyId.value, signal);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
  watch(
    batch.data,
    (value) => {
      if (pinnedBatch.value && value) setSavedStrategy(value.strategy_id);
    },
    { immediate: true },
  );
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
    if (weekly.value || !strategyId.value || generating.value) return;
    pinnedBatch.value = '';
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
              ? 'Review your strategy, offering topics and ICP selections. Selected industries or countries cannot also be excluded. Use explicit countries for geography; region filters and exclusions are not supported.'
              : 'Recommendations could not be generated. Try again.';
    } finally {
      if (started === version) generating.value = false;
    }
  }
  return {
    identity,
    weeklyHistory,
    historyOffset,
    pinnedBatch,
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
