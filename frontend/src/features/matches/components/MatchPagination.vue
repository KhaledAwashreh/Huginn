<script setup lang="ts">
import Button from 'primevue/button';

defineProps<{
  hasMore: boolean;
  offset: number;
  pageSize: number;
  fetching?: boolean;
}>();
const emit = defineEmits<{ previous: []; next: []; firstPage: [] }>();
</script>

<template>
  <nav v-if="offset > 0 || hasMore" class="pagination" aria-label="Match pages">
    <Button
      label="Previous page"
      severity="secondary"
      size="small"
      :disabled="offset === 0 || fetching"
      @click="emit('previous')"
    />
    <span>Page {{ Math.floor(offset / pageSize) + 1 }}</span>
    <Button
      label="Next page"
      severity="secondary"
      size="small"
      :disabled="!hasMore || fetching"
      @click="emit('next')"
    />
    <Button
      v-if="offset > 0"
      label="First page"
      severity="secondary"
      size="small"
      :disabled="fetching"
      @click="emit('firstPage')"
    />
  </nav>
</template>

<style scoped>
.pagination {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  font-size: 0.875rem;
}
</style>
