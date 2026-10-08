<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <header class="page-header">
    <div class="page-header__copy">
      <h1 tabindex="-1">{{ title }}</h1>
      <p v-if="description" class="page-header__description">{{ description }}</p>
    </div>
    <div v-if="$slots.default" class="page-header__actions">
      <slot />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-block: var(--space-6);
}

.page-header__copy {
  min-width: 0;
}

h1 {
  margin: 0;
  color: var(--color-text);
  font-size: 1.5rem;
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.page-header__description {
  margin: var(--space-2) 0 0;
  color: var(--color-text-muted);
}

.page-header__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}

@media (max-width: 480px) {
  .page-header {
    flex-direction: column;
  }

  .page-header__actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}
</style>
