import { computed, reactive, ref, shallowRef, watch } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import { ApiError } from '../../../api/apiError';
import { useSession } from '../../session/composables/useSession';
import { listDiscoveryStrategies } from '../../configuration/discovery-strategies/api/listDiscoveryStrategies';
import { generateRecommendations } from '../api/generateRecommendations';
import { getBusinessRecommendationPreferences } from '../api/getBusinessRecommendationPreferences';
import { listRecommendations } from '../api/listRecommendations';
import { listSuppressions } from '../api/listSuppressions';
import type { RecommendationPreferences, RecommendationStatusFilter } from '../models/prospecting';
import {
  createRecommendationCommandDraft,
  hasRecommendationFeedbackDraft,
  type RecommendationCommandDraft,
} from '../models/recommendationCommandDraft';
import type { RecommendationCommandRecovery } from '../models/recommendationCommandDraft';

const commandDraftRegistry = new Map<string, Map<string, RecommendationCommandDraft>>();

function draftsForIdentity(identity: string): Map<string, RecommendationCommandDraft> {
  let drafts = commandDraftRegistry.get(identity);
  if (!drafts) {
    drafts = reactive(new Map<string, RecommendationCommandDraft>());
    commandDraftRegistry.set(identity, drafts);
  }
  return drafts;
}
export const RECOMMENDATION_PAGE_SIZE = 25;
export const SUPPRESSION_PAGE_SIZE = 25;

export function useRecommendationWorkspace() {
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
  const search = ref('');
  const status = ref<RecommendationStatusFilter>('open');
  const offset = ref(0);
  const suppressionSearch = ref('');
  const suppressionOffset = ref(0);
  const suppressionsVisible = ref(false);
  const generationError = ref('');
  const generationResult = ref<Awaited<ReturnType<typeof generateRecommendations>> | null>(null);
  const generating = ref(false);
  const commandDrafts = shallowRef(draftsForIdentity(identity.value));
  const recommendationsKey = computed(
    () =>
      [
        'prospecting',
        identity.value,
        'recommendations',
        strategyId.value,
        status.value,
        search.value.trim(),
        offset.value,
      ] as const,
  );
  const suppressionsKey = computed(
    () =>
      [
        'prospecting',
        identity.value,
        'suppressions',
        suppressionSearch.value.trim(),
        suppressionOffset.value,
      ] as const,
  );
  const recommendations = useQuery({
    queryKey: recommendationsKey,
    enabled: computed(() => Boolean(session.context.value && strategyId.value)),
    queryFn: ({ signal }) =>
      listRecommendations(
        {
          strategyId: strategyId.value,
          status: status.value,
          search: search.value.trim(),
          offset: offset.value,
          limit: RECOMMENDATION_PAGE_SIZE,
        },
        signal,
      ),
  });
  const preferences = useQuery({
    queryKey: computed(() => ['prospecting', identity.value, 'preferences']),
    enabled: computed(() => Boolean(session.context.value)),
    queryFn: ({ signal }) => getBusinessRecommendationPreferences(signal),
  });
  const suppressions = useQuery({
    queryKey: suppressionsKey,
    enabled: computed(() => Boolean(session.context.value && suppressionsVisible.value)),
    queryFn: ({ signal }) =>
      listSuppressions(
        {
          search: suppressionSearch.value.trim(),
          offset: suppressionOffset.value,
          limit: SUPPRESSION_PAGE_SIZE,
        },
        signal,
      ),
  });
  const strategies = useQuery({
    queryKey: computed(() => ['prospecting', identity.value, 'strategies']),
    enabled: computed(() => Boolean(session.context.value)),
    queryFn: async ({ signal }) => {
      const items = [];
      let pageOffset = 0;
      let more = true;
      while (more) {
        const page = await listDiscoveryStrategies(pageOffset, 100, true, signal);
        items.push(...page.items);
        more = page.has_more;
        pageOffset += page.limit;
      }
      return items;
    },
  });

  watch(
    [strategyId, search, status],
    () => {
      offset.value = 0;
    },
    { flush: 'sync' },
  );
  watch([suppressionSearch], () => {
    suppressionOffset.value = 0;
  });
  watch(
    identity,
    (nextIdentity, previousIdentity) => {
      strategyId.value = '';
      commandDraftRegistry.delete(previousIdentity);
      commandDrafts.value = draftsForIdentity(nextIdentity);
      search.value = '';
      status.value = 'open';
      offset.value = 0;
      suppressionSearch.value = '';
      suppressionOffset.value = 0;
      generationError.value = '';
      generationResult.value = null;
      generating.value = false;
    },
    { flush: 'sync' },
  );

  function commandDraftFor(recommendationId: string): RecommendationCommandDraft {
    const existing = commandDrafts.value.get(recommendationId);
    if (existing) return existing;
    const draft = reactive(createRecommendationCommandDraft(recommendationId));
    commandDrafts.value.set(recommendationId, draft);
    return draft;
  }

  const commandRecoveries = computed<RecommendationCommandRecovery[]>(() =>
    [...commandDrafts.value.values()].flatMap((draft) => {
      const decisionDraft = Boolean(
        draft.intent ||
        draft.status !== 'idle' ||
        draft.reason.trim() ||
        draft.pauseChoice !== 'x1' ||
        draft.laterConfirmationOpen,
      );
      const feedbackDraft = hasRecommendationFeedbackDraft(draft.feedback);
      if ((!decisionDraft && !feedbackDraft) || !draft.snapshot) return [];
      return [
        {
          recommendationId: draft.recommendationId,
          snapshot: draft.snapshot,
          draft,
          decisionDraft,
          feedbackDraft,
        },
      ];
    }),
  );

  function setOffset(next: number): void {
    offset.value = Math.max(0, next);
  }

  function setSuppressionOffset(next: number): void {
    suppressionOffset.value = Math.max(0, next);
  }

  async function refresh(): Promise<void> {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['prospecting', identity.value, 'recommendations'] }),
      client.invalidateQueries({ queryKey: ['prospecting', identity.value, 'suppressions'] }),
      client.invalidateQueries({ queryKey: ['prospecting', identity.value, 'preferences'] }),
    ]);
  }

  async function refreshPreferences(): Promise<RecommendationPreferences> {
    const requestedIdentity = identity.value;
    const result = await preferences.refetch();
    if (requestedIdentity !== identity.value)
      throw new Error('The session changed while refreshing Business repeat timing.');
    if (result.isError || !result.data)
      throw result.error ?? new Error('Business repeat timing is unavailable.');
    return result.data;
  }

  async function generate(strategyId: string): Promise<boolean> {
    if (!strategyId || !session.context.value || generating.value) return false;
    const requestIdentity = identity.value;
    generating.value = true;
    generationError.value = '';
    generationResult.value = null;
    try {
      const result = await generateRecommendations(strategyId, 10);
      if (requestIdentity !== identity.value) return false;
      generationResult.value = result;
      await client.invalidateQueries({ queryKey: recommendationsKey.value });
      return requestIdentity === identity.value;
    } catch (error) {
      if (requestIdentity === identity.value) {
        generationError.value =
          error instanceof ApiError && error.status === 422
            ? 'Review the selected strategy, offerings, and ICPs before generating recommendations.'
            : error instanceof ApiError && error.status === 429
              ? 'The generation limit was reached. Wait before trying again.'
              : 'Recommendations could not be generated. Try again.';
      }
      return false;
    } finally {
      if (requestIdentity === identity.value) generating.value = false;
    }
  }

  return {
    identity,
    commandDraftFor,
    commandRecoveries,
    strategyId,
    search,
    status,
    offset,
    recommendations,
    recommendationsKey,
    preferences,
    suppressions,
    suppressionsVisible,
    suppressionSearch,
    suppressionOffset,
    suppressionsKey,
    strategies,
    generating,
    generationError,
    generationResult,
    setOffset,
    setSuppressionOffset,
    refresh,
    refreshPreferences,
    generate,
  };
}
