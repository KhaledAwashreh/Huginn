<script setup lang="ts">
defineProps<{
  message: string;
}>();
</script>

<template>
  <section class="error-state" role="alert">
    <p>{{ message }}</p>
    <div v-if="$slots.default" class="error-state__actions">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.error-state {
  display: grid;
  justify-items: start;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-card);
  background: var(--color-danger-surface);
  color: var(--color-danger-text);
}

p {
  margin: 0;
  overflow-wrap: anywhere;
}

.error-state__actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
</style>
