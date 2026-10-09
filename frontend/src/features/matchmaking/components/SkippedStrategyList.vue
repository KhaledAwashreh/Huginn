<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import Button from 'primevue/button';
import { useSession } from '../../session/composables/useSession';
import { listSkippedStrategies } from '../api/listSkippedStrategies';
const props = defineProps<{ runId: string; userId: string; label: string }>();
const session = useSession();
const queryClient = useQueryClient();
const offset = ref(0);
const limit = 20;
const key = computed(
  () =>
    [
      'admin',
      'matchmaking',
      session.context.value?.account_id,
      'skipped',
      props.runId,
      props.userId,
      offset.value,
    ] as const,
);
const page = useQuery({
  queryKey: key,
  enabled: computed(() => session.isAdministrator.value),
  queryFn: ({ signal }) =>
    listSkippedStrategies({
      runId: props.runId,
      userId: props.userId,
      offset: offset.value,
      limit,
      signal,
    }),
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
});
function onVisibilityChange() {
  if (document.visibilityState === 'hidden')
    void queryClient.cancelQueries({ queryKey: key.value });
  else if (session.isAdministrator.value) void page.refetch();
}
onMounted(() => document.addEventListener('visibilitychange', onVisibilityChange));
onBeforeUnmount(() => document.removeEventListener('visibilitychange', onVisibilityChange));
</script>

<template>
  <section class="skipped-list" :aria-label="label">
    <p v-if="page.isPending.value">Loading skipped strategies…</p>
    <p v-else-if="page.isError.value && !page.data.value" role="alert">
      Skipped strategy details could not be loaded.
      <Button
        label="Retry skipped strategies"
        :disabled="page.isFetching.value"
        @click="page.refetch()"
      />
    </p>
    <p v-if="page.isError.value && page.data.value" role="alert">
      Refresh failed. The last received skipped strategies remain visible.
      <Button
        label="Retry skipped strategies"
        :disabled="page.isFetching.value"
        @click="page.refetch()"
      />
    </p>
    <p v-else-if="!page.data.value?.items.length">No skipped strategies recorded.</p>
    <ul v-else>
      <li v-for="item in page.data.value.items" :key="item.strategy_id">
        <code>{{ item.strategy_id }}</code> · {{ item.reason }}
      </li>
    </ul>
    <div class="pager">
      <button type="button" :disabled="offset === 0" @click="offset = Math.max(0, offset - limit)">
        Previous</button
      ><span>Page {{ Math.floor(offset / limit) + 1 }}</span
      ><button type="button" :disabled="!page.data.value?.has_more" @click="offset += limit">
        More
      </button>
    </div>
  </section>
</template>

<style scoped>
.skipped-list ul {
  padding-left: 1.2rem;
}
.skipped-list li {
  overflow-wrap: anywhere;
  margin: 0.35rem 0;
}
.pager {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}
</style>
