<script setup lang="ts">
import { computed } from 'vue';
import { RouterView, useRoute, useRouter } from 'vue-router';
import Tabs from 'primevue/tabs';
import TabList from 'primevue/tablist';
import Tab from 'primevue/tab';
import TabPanels from 'primevue/tabpanels';
import TabPanel from 'primevue/tabpanel';
import PageHeader from '../../shared/ui/PageHeader.vue';
import { useSession } from '../../features/session/composables/useSession';
const session = useSession();
const route = useRoute();
const router = useRouter();
const sections = [
  { label: 'Overview', path: '/admin' },
  { label: 'Data collection', path: '/admin/pipeline' },
  { label: 'Matchmaking', path: '/admin/matchmaking' },
];
const activeSection = computed(
  () =>
    sections.find(
      (section) =>
        section.path !== '/admin' &&
        (route.path === section.path || route.path.startsWith(`${section.path}/`)),
    )?.path ?? '/admin',
);
function selectSection(value: string | number): void {
  if (sections.some((section) => section.path === value)) void router.push(String(value));
}
</script>
<template>
  <template v-if="session.isAdministrator.value">
    <p class="administration-context">Administration</p>
    <Tabs scrollable :value="activeSection" @update:value="selectSection">
      <TabList aria-label="Administration sections">
        <Tab v-for="section in sections" :key="section.path" :value="section.path">{{
          section.label
        }}</Tab>
      </TabList>
      <TabPanels>
        <TabPanel v-for="section in sections" :key="section.path" :value="section.path">
          <RouterView v-if="activeSection === section.path" />
        </TabPanel>
      </TabPanels>
    </Tabs>
  </template>
  <PageHeader
    v-else
    title="Administrator access required"
    description="Your session cannot access administration tools."
  />
</template>
<style scoped>
.administration-context {
  margin-block: var(--space-4);
  color: var(--color-text-muted);
  font-weight: 600;
}
</style>
