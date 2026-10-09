<script setup lang="ts">
import { RouterLink } from 'vue-router';
import AppNavigation from './AppNavigation.vue';
import LogoutAction from '../../features/session/components/LogoutAction.vue';
</script>

<template>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/">Huginn</RouterLink>
      <AppNavigation />
      <div class="sidebar-footer"><LogoutAction /></div>
    </aside>

    <div class="main-column">
      <header class="mobile-header">
        <RouterLink class="brand" to="/">Huginn</RouterLink>
        <AppNavigation />
        <LogoutAction />
      </header>
      <main id="main-content" class="workspace-content" tabindex="-1"><slot /></main>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 264px minmax(0, 1fr);
}
.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  min-height: 520px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
}
.brand {
  min-height: 72px;
  display: flex;
  align-items: center;
  padding: 0 var(--space-6);
  color: var(--color-primary);
  font-size: 20px;
  font-weight: 700;
  text-decoration: none;
}
.sidebar-footer {
  margin-top: auto;
  padding: var(--space-4);
  border-top: 1px solid var(--color-border);
}
.main-column {
  min-width: 0;
}
.mobile-header {
  display: none;
}
.workspace-content {
  width: min(100%, var(--content-max-width));
  margin: 0 auto;
  padding: var(--space-6);
}
.skip-link {
  position: fixed;
  left: var(--space-4);
  top: -80px;
  z-index: 1000;
  padding: var(--space-3);
  background: var(--color-surface);
  color: var(--color-primary);
}
.skip-link:focus {
  top: var(--space-2);
}

@media (max-width: 899px) {
  .app-shell {
    display: block;
  }
  .sidebar {
    display: none;
  }
  .mobile-header {
    min-height: 72px;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
  }
  .mobile-header .brand {
    min-height: 44px;
    padding: 0;
    margin-right: auto;
  }
  .workspace-content {
    padding: var(--space-4);
  }
}
</style>
