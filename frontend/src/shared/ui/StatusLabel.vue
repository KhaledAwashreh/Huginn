<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  status: string;
}>();

const tone = computed(() => {
  const normalized = props.status.toLocaleLowerCase();
  if (['success', 'active', 'ready', 'completed'].includes(normalized)) return 'success';
  if (['failed', 'failure', 'error', 'disabled'].includes(normalized)) return 'danger';
  if (['warning', 'degraded', 'paused', 'pending'].includes(normalized)) return 'warning';
  return 'neutral';
});
</script>

<template>
  <span class="status-label" :class="`status-label--${tone}`" role="status">{{ status }}</span>
</template>

<style scoped>
.status-label {
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  padding: 2px var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface-muted);
  color: var(--color-text);
  font-size: 0.875rem;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.status-label--success {
  border-color: var(--color-success-border);
  background: var(--color-success-surface);
  color: var(--color-success-text);
}

.status-label--warning {
  border-color: var(--color-warning-border);
  background: var(--color-warning-surface);
  color: var(--color-warning-text);
}

.status-label--danger {
  border-color: var(--color-danger-border);
  background: var(--color-danger-surface);
  color: var(--color-danger-text);
}
</style>
