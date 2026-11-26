<script setup lang="ts">
import { CircleAlert, CircleCheck } from '@lucide/vue';

defineProps<{
  success?: string;
  error?: string;
}>();
</script>

<template>
  <div>
    <div role="status" aria-atomic="true">
      <div v-if="success" class="feedback success">
        <CircleCheck :size="18" aria-hidden="true" />
        <span>{{ success }}</span>
      </div>
    </div>
    <div role="alert" aria-atomic="true">
      <div v-if="error" class="feedback error">
        <CircleAlert :size="18" aria-hidden="true" />
        <span>{{ error }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.feedback {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid;
  border-radius: var(--radius-control);
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}
.feedback svg {
  flex-shrink: 0;
  margin-top: 2px;
}
.success {
  color: var(--color-success-text);
  background: var(--color-success-surface);
  border-color: var(--color-success-border);
}
.error {
  color: var(--color-danger-text);
  background: var(--color-danger-surface);
  border-color: var(--color-danger-border);
}
</style>
