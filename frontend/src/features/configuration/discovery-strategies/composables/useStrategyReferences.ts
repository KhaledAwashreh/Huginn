import { computed, toValue, type MaybeRefOrGetter } from 'vue';
import { useInfiniteQuery, useQuery } from '@tanstack/vue-query';
import { useSession } from '../../../session/composables/useSession';
import { listServiceOfferings } from '../../offerings/api/listServiceOfferings';
import { getServiceOffering } from '../../offerings/api/getServiceOffering';
import { listIdealClientProfiles } from '../../ideal-client-profiles/api/listIdealClientProfiles';
import { getIdealClientProfile } from '../../ideal-client-profiles/api/getIdealClientProfile';
export function useStrategyReferences(
  offeringId: MaybeRefOrGetter<string>,
  icpId: MaybeRefOrGetter<string>,
) {
  const session = useSession();
  const scope = computed(() => [
    'configuration',
    session.context.value?.account_id,
    session.context.value?.user_id,
    'strategy-references',
  ]);
  const enabled = computed(() => session.context.value !== null);
  const offerings = useInfiniteQuery({
    queryKey: computed(() => [...scope.value, 'offerings']),
    enabled,
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => listServiceOfferings(pageParam, 100, signal),
    getNextPageParam: (page) => (page.has_more ? page.offset + page.limit : undefined),
    retry: false,
  });
  const icps = useInfiniteQuery({
    queryKey: computed(() => [...scope.value, 'icps']),
    enabled,
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => listIdealClientProfiles(pageParam, 100, signal),
    getNextPageParam: (page) => (page.has_more ? page.offset + page.limit : undefined),
    retry: false,
  });
  const offeringItems = computed(
    () => offerings.data.value?.pages.flatMap((page) => page.items) ?? [],
  );
  const icpItems = computed(() => icps.data.value?.pages.flatMap((page) => page.items) ?? []);
  const selectedOffering = useQuery({
    queryKey: computed(() => [...scope.value, 'selected-offering', toValue(offeringId)]),
    enabled: computed(
      () =>
        enabled.value &&
        Boolean(toValue(offeringId)) &&
        !offerings.isPending.value &&
        !offeringItems.value.some((item) => item.id === toValue(offeringId)),
    ),
    queryFn: ({ signal }) => getServiceOffering(toValue(offeringId), signal),
    retry: false,
  });
  const selectedIcp = useQuery({
    queryKey: computed(() => [...scope.value, 'selected-icp', toValue(icpId)]),
    enabled: computed(
      () =>
        enabled.value &&
        Boolean(toValue(icpId)) &&
        !icps.isPending.value &&
        !icpItems.value.some((item) => item.id === toValue(icpId)),
    ),
    queryFn: ({ signal }) => getIdealClientProfile(toValue(icpId), signal),
    retry: false,
  });
  return { offerings, icps, offeringItems, icpItems, selectedOffering, selectedIcp };
}
