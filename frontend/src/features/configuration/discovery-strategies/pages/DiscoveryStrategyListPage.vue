<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import Button from 'primevue/button';
import Select from 'primevue/select';
import Dialog from 'primevue/dialog';
import PageHeader from '../../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import EmptyState from '../../../../shared/ui/EmptyState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import StatusLabel from '../../../../shared/ui/StatusLabel.vue';
import { ApiError } from '../../../../api/apiError';
import { useSession } from '../../../session/composables/useSession';
import { listDiscoveryStrategies } from '../api/listDiscoveryStrategies';
import { useDiscoveryStrategy } from '../composables/useDiscoveryStrategy';
const session = useSession();
const offset = ref(0);
const active = ref<'all' | 'active' | 'inactive'>('all');
const filters = [
  { label: 'All strategies', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Inactive', value: 'inactive' },
];
watch(active, () => {
  offset.value = 0;
});
const query = useQuery({
  queryKey: computed(() => [
    'configuration',
    session.context.value?.account_id,
    session.context.value?.user_id,
    'strategies',
    'list',
    offset.value,
    active.value,
  ]),
  enabled: computed(() => Boolean(session.context.value)),
  queryFn: ({ signal }) =>
    listDiscoveryStrategies(
      offset.value,
      100,
      active.value === 'all' ? undefined : active.value === 'active',
      signal,
    ),
  retry: false,
});
const state = useDiscoveryStrategy(undefined);
const deleting = ref<{ id: string; name: string } | null>(null);
const message = ref('');
const deleteNeedsRefresh = ref(false);
async function refreshList(): Promise<void> {
  const result = await query.refetch();
  if (!result.isError) deleteNeedsRefresh.value = false;
}
async function remove(): Promise<void> {
  if (!deleting.value || state.remove.isPending.value || deleteNeedsRefresh.value) return;
  try {
    await state.remove.mutateAsync(deleting.value.id);
    deleting.value = null;
    message.value = 'Strategy deleted.';
    if ((query.data.value?.items.length ?? 0) <= 1 && offset.value)
      offset.value = Math.max(0, offset.value - 100);
  } catch (error) {
    message.value =
      error instanceof ApiError && error.status < 500
        ? error.message
        : 'The delete response was lost. Refresh the list before deciding whether to delete again.';
    deleteNeedsRefresh.value = !(error instanceof ApiError && error.status < 500);
    deleting.value = null;
  }
}
</script>
<template>
  <PageHeader
    title="Discovery strategies"
    description="Manage the definitions used by future matching runs."
    ><RouterLink to="/strategies/new">Create strategy</RouterLink></PageHeader
  >
  <div class="list-filter">
    <label for="strategy-filter">Activity</label
    ><Select
      v-model="active"
      input-id="strategy-filter"
      :options="filters"
      option-label="label"
      option-value="value"
    />
  </div>
  <p v-if="message" role="status">{{ message }}</p>
  <Button
    v-if="deleteNeedsRefresh"
    label="Refresh saved list"
    severity="secondary"
    :disabled="query.isFetching.value"
    @click="refreshList"
  />
  <LoadingState v-if="query.isPending.value" />
  <ErrorState
    v-else-if="query.isError.value"
    :message="query.error.value?.message ?? 'Strategies could not be loaded.'"
    ><Button label="Refresh list" @click="refreshList"
  /></ErrorState>
  <template v-else-if="query.data.value">
    <EmptyState
      v-if="!query.data.value.items.length"
      message="No strategies yet. Create a strategy to link an offering and an ICP."
    />
    <div v-else class="configuration-table-wrap">
      <table class="configuration-table">
        <caption class="visually-hidden">
          Your discovery strategies
        </caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Status</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in query.data.value.items" :key="item.id">
            <td>{{ item.name }}</td>
            <td><StatusLabel :status="item.is_active ? 'Active' : 'Inactive'" /></td>
            <td class="table-actions">
              <RouterLink :to="`/strategies/${item.id}`"
                >Edit <span class="visually-hidden">{{ item.name }}</span></RouterLink
              ><Button
                label="Delete"
                :disabled="deleteNeedsRefresh"
                severity="danger"
                :aria-label="`Delete ${item.name}`"
                @click="
                  deleting = item;
                  message = '';
                "
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pagination">
      <Button
        label="Previous page"
        severity="secondary"
        :disabled="offset === 0 || query.isFetching.value"
        @click="offset = Math.max(0, offset - 100)"
      /><span>Page {{ Math.floor(offset / 100) + 1 }}</span
      ><Button
        label="Next page"
        severity="secondary"
        :disabled="!query.data.value.has_more || query.isFetching.value"
        @click="offset += 100"
      /><Button
        label="Refresh list"
        severity="secondary"
        :disabled="query.isFetching.value"
        @click="refreshList"
      />
    </div>
  </template>
  <Dialog
    :visible="Boolean(deleting)"
    modal
    header="Delete strategy?"
    :closable="!state.remove.isPending.value"
    @update:visible="!state.remove.isPending.value && (deleting = null)"
    ><p>Delete {{ deleting?.name }}? This cannot be undone.</p>
    <div class="form-actions">
      <Button
        label="Keep strategy"
        severity="secondary"
        :disabled="state.remove.isPending.value"
        @click="deleting = null"
      /><Button
        label="Delete strategy"
        severity="danger"
        :loading="state.remove.isPending.value"
        :disabled="state.remove.isPending.value"
        @click="remove"
      /></div
  ></Dialog>
</template>
