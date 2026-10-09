<script setup lang="ts">
import { ref, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import { useTargetUsers } from '../composables/useTargetUsers';
import type { components } from '../../../api/generated/schema';

type TargetUser = components['schemas']['TargetUserResponse'];
const props = defineProps<{ modelValue: TargetUser | undefined }>();
const emit = defineEmits<{ 'update:modelValue': [value: TargetUser | undefined] }>();
const search = ref('');
const offset = ref(0);
const { users, pageSize } = useTargetUsers(
  () => search.value,
  () => offset.value,
);
watch(search, () => (offset.value = 0));
</script>

<template>
  <section class="target-picker" aria-label="Choose a matchmaking target user">
    <label for="target-search">Search active users</label>
    <InputText
      id="target-search"
      v-model="search"
      type="search"
      maxlength="200"
      placeholder="Name, username, or exact user ID"
    />
    <p v-if="users.data.value">
      {{ users.data.value.total_eligible_count }} users are currently eligible. This preview can
      change before the run is accepted.
    </p>
    <div v-if="props.modelValue" class="selected-user">
      <strong>Selected:</strong> {{ props.modelValue.username }}
      <span>({{ props.modelValue.id }})</span>
      <Button
        type="button"
        label="Clear selection"
        severity="secondary"
        @click="emit('update:modelValue', undefined)"
      />
    </div>
    <LoadingState v-if="users.isPending.value" message="Searching active users…" />
    <ErrorState
      v-else-if="users.isError.value && !users.data.value"
      message="Active users could not be loaded."
    >
      <Button
        label="Retry user search"
        :disabled="users.isFetching.value"
        @click="users.refetch()"
      />
    </ErrorState>
    <p v-if="users.isError.value && users.data.value" role="alert">
      Search refresh failed. The last received user page remains visible.
    </p>
    <ul v-if="users.data.value?.items.length" class="user-options">
      <li v-for="user in users.data.value.items" :key="user.id">
        <Button
          unstyled
          type="button"
          :aria-pressed="props.modelValue?.id === user.id"
          @click="emit('update:modelValue', user)"
        >
          <span>{{ user.username }}</span
          ><small
            >{{
              [user.first_name, user.last_name].filter(Boolean).join(' ') || 'Name unavailable'
            }}
            · {{ user.has_active_strategies ? 'Has active strategies' : 'No active strategies' }} ·
            {{ user.id }}</small
          >
        </Button>
      </li>
    </ul>
    <EmptyState
      v-else-if="users.data.value && !users.data.value.items.length"
      :message="search ? 'No active users match this search.' : 'No active users are available.'"
    />
    <div class="pager">
      <Button
        type="button"
        label="Previous users"
        severity="secondary"
        :disabled="offset === 0"
        @click="offset = Math.max(0, offset - pageSize)"
      />
      <span>Users {{ offset + 1 }}–{{ offset + (users.data.value?.items.length ?? 0) }}</span>
      <Button
        type="button"
        label="More users"
        severity="secondary"
        :disabled="!users.data.value?.has_more"
        @click="offset += pageSize"
      />
    </div>
  </section>
</template>

<style scoped>
.target-picker {
  display: grid;
  gap: 0.65rem;
}
.target-picker input {
  width: 100%;
}
.user-options {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.35rem;
  max-height: 15rem;
  overflow: auto;
}
.user-options button {
  display: flex;
  flex-direction: column;
  width: 100%;
  align-items: flex-start;
  padding: 0.65rem;
  text-align: left;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
}
.user-options button[aria-pressed='true'] {
  border-color: var(--color-primary);
  background: var(--color-success-surface);
}
.user-options small,
.selected-user span {
  color: var(--color-text-muted);
  overflow-wrap: anywhere;
}
.selected-user,
.pager {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.65rem;
}
.pager {
  justify-content: space-between;
}
</style>
