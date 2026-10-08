<script setup lang="ts">
withDefaults(
  defineProps<{
    message?: string;
  }>(),
  { message: 'Loading…' },
);
</script>

<template>
  <div class="loading-state" role="status" aria-live="polite" aria-busy="true">
    <span class="loading-state__indicator" aria-hidden="true"></span>
    <span>{{ message }}</span>
  </div>
</template>

<style scoped>
.loading-state {
  display: flex;
  min-height: 48px;
  align-items: center;
  gap: var(--space-3);
  color: var(--color-text-muted);
}

.loading-state__indicator {
  width: 1rem;
  height: 1rem;
  flex: 0 0 auto;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: loading-spin 800ms linear infinite;
}

@keyframes loading-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .loading-state__indicator {
    animation: none;
  }
}
</style>
