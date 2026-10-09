<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import PageHeader from '../../../../shared/ui/PageHeader.vue';
import EmptyState from '../../../../shared/ui/EmptyState.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import { ApiError } from '../../../../api/apiError';
import { useIdealClientProfile } from '../composables/useIdealClientProfile';

const router = useRouter();
const offset = ref(0);
const limit = 100;
const { list, remove } = useIdealClientProfile(undefined, offset, limit);
const selected = ref<{ id: string; name: string } | null>(null);
const error = ref('');
const deleteNeedsRefresh = ref(false);
const canPrevious = computed(() => offset.value > 0);
async function confirmDelete(): Promise<void> {
  if (!selected.value || remove.isPending.value) return;
  error.value = '';
  deleteNeedsRefresh.value = false;
  try {
    await remove.mutateAsync(selected.value.id);
    if ((list.data.value?.items.length ?? 0) <= 1 && offset.value >= limit)
      offset.value = Math.max(0, offset.value - limit);
    selected.value = null;
  } catch (failure) {
    error.value =
      failure instanceof ApiError && failure.status === 409
        ? 'This ICP is used by a discovery strategy. Update or remove that strategy reference first.'
        : failure instanceof ApiError && failure.status < 500
          ? failure.message
          : 'The delete outcome is uncertain. Refresh the list before deciding what to do next.';
    deleteNeedsRefresh.value = !(failure instanceof ApiError && failure.status < 500);
  }
}
async function refreshAfterUncertainDelete(): Promise<void> {
  if (list.isFetching.value) return;
  const result = await list.refetch();
  if (result.isError || !result.data) {
    error.value =
      'The list could not be refreshed. Keep this dialog open and try Refresh list again.';
    return;
  }
  selected.value = null;
  deleteNeedsRefresh.value = false;
  error.value = '';
}
</script>
<template>
  <section>
    <PageHeader
      title="Ideal client profiles"
      description="Describe the companies you want to reach and the exclusions to apply."
      ><Button label="Add ICP" @click="router.push('/icps/new')"
    /></PageHeader>
    <ErrorState v-if="error" :message="error" />
    <LoadingState v-if="list.isPending.value" message="Loading ICPs…" />
    <ErrorState
      v-else-if="list.isError.value"
      message="ICPs could not be loaded. Reload the list to try again."
    />
    <EmptyState
      v-else-if="list.data.value?.items.length === 0 && offset === 0"
      message="No ICPs yet. Add an ideal client profile to define a target audience."
    />
    <div v-else-if="list.data.value" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Criteria</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in list.data.value.items" :key="item.id">
            <th scope="row">{{ item.name }}</th>
            <td class="criteria">
              <span
                >Industries:
                {{ item.industries.map((entry) => entry.name).join(', ') || 'Any' }}</span
              ><span
                >Company sizes:
                {{ item.company_sizes.map((entry) => entry.band).join(', ') || 'Any' }}</span
              ><span
                >Geographies:
                {{
                  item.geographies.map((entry) => `${entry.kind}: ${entry.value}`).join(', ') ||
                  'Any'
                }}</span
              ><span>Exclusions: {{ item.exclusions.length }}</span>
            </td>
            <td class="actions">
              <Button
                label="Edit"
                severity="secondary"
                @click="router.push(`/icps/${item.id}`)"
              /><Button
                label="Delete"
                severity="danger"
                @click="
                  error = '';
                  deleteNeedsRefresh = false;
                  selected = { id: item.id, name: item.name };
                "
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <nav v-if="list.data.value" class="pagination" aria-label="ICP pages">
      <Button
        label="Previous"
        severity="secondary"
        :disabled="!canPrevious"
        @click="offset = Math.max(0, offset - limit)"
      /><span>Showing {{ offset + 1 }}–{{ offset + list.data.value.items.length }}</span
      ><Button
        label="Next"
        severity="secondary"
        :disabled="!list.data.value.has_more"
        @click="offset += limit"
      />
    </nav>
    <Dialog
      :visible="selected !== null"
      modal
      header="Delete ICP?"
      :style="{ width: 'min(32rem, calc(100vw - 2rem))' }"
      @update:visible="
        (visible) => {
          if (!visible && !remove.isPending.value && !deleteNeedsRefresh) {
            selected = null;
            error = '';
          }
        }
      "
      ><p v-if="selected">Delete “{{ selected.name }}”? This cannot be undone.</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <div class="dialog-actions">
        <Button
          v-if="deleteNeedsRefresh"
          label="Refresh list"
          severity="secondary"
          :disabled="list.isFetching.value"
          @click="refreshAfterUncertainDelete"
        /><Button
          v-if="!deleteNeedsRefresh"
          label="Keep ICP"
          severity="secondary"
          :disabled="remove.isPending.value"
          @click="selected = null"
        /><Button
          v-if="!deleteNeedsRefresh"
          label="Delete ICP"
          severity="danger"
          :loading="remove.isPending.value"
          @click="confirmDelete"
        /></div
    ></Dialog>
  </section>
</template>
<style scoped>
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
}
table {
  border-collapse: collapse;
  width: 100%;
  min-width: 640px;
}
th,
td {
  text-align: left;
  vertical-align: top;
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  overflow-wrap: anywhere;
}
thead {
  background: var(--color-surface-muted);
}
.criteria {
  display: grid;
  min-width: 20rem;
  gap: var(--space-1);
}
.actions,
.dialog-actions,
.pagination {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.pagination {
  justify-content: flex-end;
  margin-top: var(--space-4);
}
.dialog-actions {
  justify-content: flex-end;
}
</style>
