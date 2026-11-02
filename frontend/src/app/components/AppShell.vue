<script setup lang="ts">
import { provide, ref } from 'vue';
import AppNavigation from './AppNavigation.vue';
import SettingsDialog from './SettingsDialog.vue';
import TopBar from './TopBar.vue';
import { pageTitleKey, type PageTitle } from '../../shared/navigation/pageTitle';
import { openSettingsKey, type SettingsSection } from '../../shared/navigation/settingsSections';

provide(pageTitleKey, ref<PageTitle | null>(null));
const settingsVisible = ref(false);
const settingsSection = ref<SettingsSection>('account');

function openSettings(section: SettingsSection): void {
  settingsSection.value = section;
  settingsVisible.value = true;
}
provide(openSettingsKey, openSettings);
</script>

<template>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <div class="app-shell">
    <header class="app-header"><AppNavigation @open-settings="openSettings" /></header>
    <main id="main-content" tabindex="-1">
      <TopBar />
      <div class="workspace-content"><slot /></div>
    </main>
  </div>
  <SettingsDialog v-model:visible="settingsVisible" v-model:section="settingsSection" />
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}
.app-header {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
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
  .workspace-content {
    padding: var(--space-4);
  }
}
</style>
