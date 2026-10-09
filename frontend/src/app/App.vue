<script setup lang="ts">
import { nextTick, watch } from 'vue';
import { RouterView, useRoute, useRouter } from 'vue-router';
import AppShell from './components/AppShell.vue';
import { useSession } from '../features/session/composables/useSession';
import { validateReturnPath } from '../shared/navigation/validateReturnPath';

const session = useSession();
const router = useRouter();
const route = useRoute();
watch(session.context, (current, previous) => {
  if (!current && previous && route.meta.requiresAuth)
    void router.replace({ name: 'login', query: { return: validateReturnPath(route.fullPath) } });
});
router.afterEach((to, from, failure) => {
  if (failure || to.path === from.path) return;
  // Route-backed administration tabs keep keyboard focus within their tab list.
  if (
    to.path.startsWith('/admin') &&
    from.path.startsWith('/admin') &&
    document.activeElement?.getAttribute('role') === 'tab'
  )
    return;
  void nextTick(() => document.querySelector<HTMLElement>('h1')?.focus());
});
</script>

<template>
  <AppShell v-if="session.isAuthenticated.value && route.meta.requiresAuth"
    ><RouterView
  /></AppShell>
  <RouterView v-else />
</template>
