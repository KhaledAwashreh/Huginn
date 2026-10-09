<script setup lang="ts">
import Select from 'primevue/select';
import type { MatchStatusFilter } from '../api/listMatches';

defineProps<{ modelValue: MatchStatusFilter | undefined }>();
const emit = defineEmits<{ 'update:modelValue': [value: MatchStatusFilter | undefined] }>();
const options = [
  { label: 'All statuses', value: null },
  { label: 'New', value: 'new' },
  { label: 'Contacted', value: 'contacted' },
  { label: 'Responded', value: 'responded' },
  { label: 'Dismissed', value: 'dismissed' },
  { label: 'Converted', value: 'converted' },
];
</script>

<template>
  <div class="match-status-filter">
    <label for="match-status">Filter by status</label>
    <Select
      input-id="match-status"
      :model-value="modelValue ?? null"
      :options="options"
      option-label="label"
      option-value="value"
      placeholder="All statuses"
      aria-label="Filter by status"
      @update:model-value="emit('update:modelValue', $event ?? undefined)"
    />
  </div>
</template>

<style scoped>
.match-status-filter {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
</style>
