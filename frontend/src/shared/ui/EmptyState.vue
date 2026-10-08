<script setup lang="ts">
withDefaults(
  defineProps<{
    message?: string;
  }>(),
  { message: 'Nothing here yet.' },
);
</script>

<template>
  <section class="empty-state" aria-live="polite">
    <p>{{ message }}</p>
    <div v-if="$slots.default" class="empty-state__actions">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.empty-state {
  display: grid;
  justify-items: start;
  gap: var(--space-3);
  padding: var(--space-5);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}

p {
  margin: 0;
  color: var(--color-text-muted);
  overflow-wrap: anywhere;
}

.empty-state__actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
</style>
