<script setup lang="ts">
import { computed, inject } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { ChevronRight } from '@lucide/vue';
import { useSession } from '../../features/session/composables/useSession';
import { pageTitleKey } from '../../shared/navigation/pageTitle';

const route = useRoute();
const session = useSession();
const pageTitle = inject(pageTitleKey, null);
// Admin trails would link to pages a demoted session can no longer open.
const breadcrumbs = computed(() =>
  route.meta.requiresAdmin && !session.isAdministrator.value ? [] : (route.meta.breadcrumbs ?? []),
);
// Pages that are still loading fall back to their navigation label.
const title = computed(() => pageTitle?.value?.title ?? route.meta.navigationLabel ?? '');
</script>

<template>
  <h1 v-if="route.meta.hideTitle" class="visually-hidden" tabindex="-1">{{ title }}</h1>
  <div v-else class="top-bar">
    <nav v-if="breadcrumbs.length" class="breadcrumbs" aria-label="Breadcrumb">
      <ol>
        <li v-for="crumb in breadcrumbs" :key="crumb.to">
          <RouterLink :to="crumb.to">{{ crumb.label }}</RouterLink>
          <ChevronRight :size="16" aria-hidden="true" />
        </li>
      </ol>
    </nav>
    <h1 tabindex="-1">{{ title }}</h1>
  </div>
</template>

<style scoped>
.top-bar {
  min-height: 52px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-2)
    max(var(--space-6), calc((100% - var(--content-max-width)) / 2 + var(--space-6)));
}
.breadcrumbs ol {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.breadcrumbs li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-muted);
}
.breadcrumbs a {
  color: var(--color-text-muted);
  font-size: 1rem;
  text-decoration: none;
}
.breadcrumbs a:hover {
  color: var(--color-text);
  text-decoration: underline;
}
h1 {
  min-width: 0;
  margin: 0;
  color: var(--color-text);
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
/* Navigation moves focus here for screen readers; the static title needs no focus ring. */
h1:focus-visible {
  outline: none;
  box-shadow: none;
}

@media (max-width: 899px) {
  .top-bar {
    min-height: 48px;
    padding: var(--space-2) var(--space-4);
  }
}
</style>
