<script setup lang="ts">
import { inject, onBeforeUnmount, watchEffect } from 'vue';
import { pageTitleKey } from '../navigation/pageTitle';

const props = defineProps<{
  title: string;
  description?: string;
}>();

// Inside the app shell the title (the page's h1) is shown in the top bar instead.
const topBarTitle = inject(pageTitleKey, null);
const owner = Symbol('PageHeader');
if (topBarTitle) {
  watchEffect(() => {
    topBarTitle.value = { owner, title: props.title };
  });
  onBeforeUnmount(() => {
    if (topBarTitle.value?.owner === owner) topBarTitle.value = null;
  });
}
</script>

<template>
  <header
    v-if="!topBarTitle || description || $slots.default"
    :class="['page-header', { 'page-header--in-shell': topBarTitle }]"
  >
    <div class="page-header__copy">
      <h1 v-if="!topBarTitle" tabindex="-1">{{ title }}</h1>
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

.page-header--in-shell {
  margin-block: 0 var(--space-6);
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
