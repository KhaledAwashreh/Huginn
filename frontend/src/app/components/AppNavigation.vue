<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, useRouter } from 'vue-router';

const router = useRouter();
const links = computed(() =>
  router.getRoutes().filter((route) => typeof route.meta.navigationLabel === 'string'),
);
</script>

<template>
  <nav class="app-navigation" aria-label="Workspace navigation">
    <RouterLink v-for="link in links" :key="link.path" :to="link.path">{{
      link.meta.navigationLabel
    }}</RouterLink>
  </nav>
</template>

<style scoped>
.app-navigation {
  width: min(100%, var(--content-max-width));
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}
a {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-control);
  color: var(--color-text-muted);
  text-decoration: none;
}
a[aria-current='page'] {
  color: var(--color-primary);
  background: #e7f2eb;
  font-weight: 600;
}
</style>
