<script setup lang="ts">
import { RouterLink } from 'vue-router';
import Card from 'primevue/card';
import Button from 'primevue/button';
import PageHeader from '../../shared/ui/PageHeader.vue';
</script>
<template>
  <PageHeader
    title="Administration"
    description="Collect company data and run matchmaking from one workspace."
  />
  <div class="administration-tools">
    <Card>
      <template #title>Data collection</template>
      <template #content
        ><p>
          Start the existing collection pipeline, follow its progress, and inspect saved results.
        </p></template
      >
      <template #footer
        ><Button
          :as="RouterLink"
          class="tool-link"
          to="/admin/pipeline"
          label="Open data collection"
      /></template>
    </Card>
    <Card>
      <template #title>Matchmaking</template>
      <template #content
        ><p>
          Trigger the matching service for a specific user or all eligible users, then review run
          outcomes.
        </p></template
      >
      <template #footer
        ><Button
          :as="RouterLink"
          class="tool-link"
          to="/admin/matchmaking"
          label="Open matchmaking"
      /></template>
    </Card>
  </div>
</template>
<style scoped>
.tool-link {
  text-decoration: none;
}
.administration-tools {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
  gap: var(--space-6);
}
</style>
