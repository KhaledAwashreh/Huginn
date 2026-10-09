<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue';
import { isNavigationFailure, RouterLink, useRoute, type NavigationFailure } from 'vue-router';
import Button from 'primevue/button';
import Drawer from 'primevue/drawer';
import Menu from 'primevue/menu';
import { useSession } from '../../features/session/composables/useSession';

type NavigationItem = {
  label: string;
  to: string;
};

const emit = defineEmits<{ navigate: [] }>();
const route = useRoute();
const session = useSession();
const drawerVisible = ref(false);
const drawerId = useId();
const isAdminRoute = computed(() => route.path === '/admin' || route.path.startsWith('/admin/'));

const workspaceItems = [
  { label: 'Workspace', to: '/' },
  { label: 'Matches', to: '/matches' },
];
const businessItems = [
  { label: 'Professional profile', to: '/professional-profile' },
  { label: 'Service offerings', to: '/offerings' },
  { label: 'ICPs', to: '/icps' },
  { label: 'Discovery strategies', to: '/strategies' },
];
const accountItems = [{ label: 'Account & security', to: '/account' }];
const administrationItems = [
  { label: 'Administration overview', to: '/admin' },
  { label: 'Data collection', to: '/admin/pipeline' },
  { label: 'Matchmaking', to: '/admin/matchmaking' },
];
const workspaceSections = computed(() => {
  const sections: { label: string; items: NavigationItem[] }[] = [
    { label: 'Workspace', items: workspaceItems },
    { label: 'Business setup', items: businessItems },
    { label: 'Account', items: accountItems },
  ];
  if (session.isAdministrator.value)
    sections.push({ label: 'Administration', items: [{ label: 'Administration', to: '/admin' }] });
  return sections;
});

const administrationSections = [
  { label: 'Administration', items: administrationItems },
  { label: 'Workspace', items: [{ label: 'Back to workspace', to: '/' }] },
];

const sections = computed(() =>
  isAdminRoute.value && session.isAdministrator.value
    ? administrationSections
    : workspaceSections.value,
);

function isActive(item: unknown): boolean {
  const target = (item as NavigationItem).to;
  if (typeof target !== 'string') return false;
  if (target === '/') return route.path === '/';
  if (target === '/admin') return route.path === '/admin';
  return route.path === target || route.path.startsWith(`${target}/`);
}

async function handleNavigate(
  event: MouseEvent,
  navigate: (event?: MouseEvent) => Promise<void | NavigationFailure>,
): Promise<void> {
  const result = await navigate(event);
  if (isNavigationFailure(result)) return;
  drawerVisible.value = false;
  emit('navigate');
}

watch(
  () => route.fullPath,
  () => {
    drawerVisible.value = false;
  },
);
</script>

<template>
  <nav
    class="app-navigation desktop-navigation"
    :aria-label="
      isAdminRoute && session.isAdministrator.value
        ? 'Administration navigation'
        : 'Workspace navigation'
    "
  >
    <section v-for="section in sections" :key="section.label" class="navigation-section">
      <h2>{{ section.label }}</h2>
      <Menu
        :model="section.items"
        class="navigation-menu"
        :dt="{ root: { borderColor: 'transparent', background: 'transparent' } }"
      >
        <template #item="{ item, props }">
          <RouterLink v-slot="{ href, navigate }" :to="item.to" custom>
            <a
              v-bind="props.action"
              :href="href"
              :class="['navigation-link', { 'navigation-link-active': isActive(item) }]"
              :aria-current="isActive(item) ? 'page' : undefined"
              @click="handleNavigate($event, navigate)"
            >
              <span>{{ item.label }}</span>
            </a>
          </RouterLink>
        </template>
      </Menu>
    </section>
  </nav>

  <div class="mobile-navigation">
    <Button
      type="button"
      label="Menu"
      aria-label="Open navigation menu"
      aria-haspopup="dialog"
      :aria-expanded="drawerVisible"
      :aria-controls="drawerId"
      @click="drawerVisible = true"
    />
    <Drawer
      :id="drawerId"
      v-model:visible="drawerVisible"
      :aria-label="
        isAdminRoute && session.isAdministrator.value
          ? 'Administration navigation'
          : 'Workspace navigation'
      "
      position="left"
      class="navigation-drawer"
      :style="{ width: 'min(20rem, 100vw)' }"
    >
      <template #header>
        <span class="drawer-title">{{ isAdminRoute ? 'Administration' : 'Workspace' }}</span>
      </template>
      <nav
        :aria-label="
          isAdminRoute && session.isAdministrator.value
            ? 'Administration navigation'
            : 'Workspace navigation'
        "
      >
        <section v-for="section in sections" :key="section.label" class="navigation-section">
          <h2>{{ section.label }}</h2>
          <Menu
            :model="section.items"
            class="navigation-menu"
            :dt="{ root: { borderColor: 'transparent', background: 'transparent' } }"
          >
            <template #item="{ item, props }">
              <RouterLink v-slot="{ href, navigate }" :to="item.to" custom>
                <a
                  v-bind="props.action"
                  :href="href"
                  :class="['navigation-link', { 'navigation-link-active': isActive(item) }]"
                  :aria-current="isActive(item) ? 'page' : undefined"
                  @click="handleNavigate($event, navigate)"
                >
                  <span>{{ item.label }}</span>
                </a>
              </RouterLink>
            </template>
          </Menu>
        </section>
      </nav>
    </Drawer>
  </div>
</template>

<style scoped>
.app-navigation {
  display: grid;
  align-content: start;
  gap: var(--space-5);
  padding: var(--space-4) var(--space-3);
}
.navigation-section h2 {
  margin: 0 0 var(--space-2);
  padding: 0 var(--space-3);
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.navigation-menu {
  border: 0;
  background: transparent;
}
.navigation-menu :deep(.p-menu-list) {
  gap: var(--space-1);
}
.navigation-menu :deep(.p-menu-item-content) {
  border-radius: var(--radius-control);
}
.navigation-link {
  position: relative;
  min-height: 42px;
  color: var(--color-text-muted);
  text-decoration: none;
}
.navigation-link-active {
  color: var(--color-primary);
  background: var(--color-surface-muted);
  font-weight: 600;
}
.navigation-link-active::before {
  position: absolute;
  left: 0;
  width: 3px;
  height: 22px;
  border-radius: 0 3px 3px 0;
  background: var(--color-primary);
  content: '';
}
.mobile-navigation {
  display: none;
}
.drawer-title {
  font-size: 18px;
  font-weight: 700;
}

@media (max-width: 899px) {
  .desktop-navigation {
    display: none;
  }
  .mobile-navigation {
    display: block;
  }
}
</style>
