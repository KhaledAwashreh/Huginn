<script setup lang="ts">
import AppNavigation from './AppNavigation.vue';
import LogoutAction from '../../features/session/components/LogoutAction.vue';
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">Skip to main content</a>
    <header class="app-header">
      <span class="brand">Huginn</span>
      <LogoutAction />
    </header>
    <AppNavigation />
    <main id="main-content" class="workspace-content" tabindex="-1"><slot /></main>
  </div>
</template>

<style scoped>
.app-header {
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4) max(var(--space-4), calc((100vw - 1120px) / 2));
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}
.brand {
  font-weight: 700;
  font-size: 20px;
  color: var(--color-primary);
}
.workspace-content {
  width: min(100%, var(--content-max-width));
  margin: 0 auto;
  padding: var(--space-4);
}
.skip-link {
  position: absolute;
  left: var(--space-4);
  top: -80px;
  z-index: 100;
  padding: var(--space-3);
  background: white;
  color: var(--color-primary);
}
.skip-link:focus {
  top: var(--space-2);
}
</style>
