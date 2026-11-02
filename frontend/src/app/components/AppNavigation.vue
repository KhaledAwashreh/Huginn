<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router';
import MegaMenu from 'primevue/megamenu';
import { Bird } from '@lucide/vue';
import UserMenu from './UserMenu.vue';
import type { SettingsSection } from '../../shared/navigation/settingsSections';

defineEmits<{ openSettings: [section: SettingsSection] }>();
const route = useRoute();

const items = [
  { label: 'Matches', to: '/matches', activePaths: ['/matches'] },
  {
    label: 'Profile',
    to: '/profile',
    activePaths: ['/profile', '/professional-profile', '/offerings'],
  },
];

function isActive(activePaths: string[]): boolean {
  return activePaths.some((path) => route.path === path || route.path.startsWith(`${path}/`));
}
</script>

<template>
  <nav class="top-nav" aria-label="Workspace navigation">
    <!-- PrimeVue sets aria-level on menu items, which that role does not allow. -->
    <MegaMenu :model="items" breakpoint="1px" :pt="{ item: { 'aria-level': null } }">
      <template #start>
        <RouterLink class="brand" to="/" aria-label="Huginn home">
          <span class="app-icon" aria-hidden="true"><Bird :size="18" :stroke-width="2" /></span>
          <span class="brand-name">Huginn</span>
        </RouterLink>
      </template>
      <template #item="{ item, props }">
        <RouterLink v-slot="{ href, navigate }" :to="item.to as string" custom>
          <a
            v-bind="props.action"
            :href="href"
            :class="['nav-link', { 'nav-link--active': isActive(item.activePaths as string[]) }]"
            :aria-current="isActive(item.activePaths as string[]) ? 'page' : undefined"
            @click="navigate"
            >{{ item.label }}</a
          >
        </RouterLink>
      </template>
      <template #end>
        <UserMenu @open="$emit('openSettings', $event)" />
      </template>
    </MegaMenu>
  </nav>
</template>

<style scoped>
.top-nav :deep(.p-megamenu) {
  min-height: 56px;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-6);
  border: 0;
  border-radius: 0;
  background: transparent;
}
.top-nav :deep(.p-megamenu-start) {
  justify-self: start;
}
.top-nav :deep(.p-megamenu-end) {
  justify-self: end;
  margin: 0;
}
.top-nav :deep(.p-megamenu-root-list) {
  display: flex;
  gap: var(--space-1);
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text);
  font-size: 1.125rem;
  font-weight: 650;
  text-decoration: none;
}
.app-icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-control);
  background: var(--color-primary);
  color: var(--color-surface);
}
.nav-link {
  min-height: 40px;
  display: flex;
  align-items: center;
  padding: 0 var(--space-4);
  border-radius: var(--radius-control);
  color: var(--color-text-muted);
  text-decoration: none;
}
.nav-link:hover {
  color: var(--color-text);
}
.nav-link--active {
  background: var(--color-surface-muted);
  color: var(--color-text);
  font-weight: 600;
}

@media (max-width: 480px) {
  .top-nav :deep(.p-megamenu) {
    padding: 0 var(--space-3);
  }
  .brand-name {
    display: none;
  }
  .nav-link {
    padding: 0 var(--space-2);
  }
}
</style>
