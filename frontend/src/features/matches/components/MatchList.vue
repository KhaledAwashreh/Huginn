<script setup lang="ts">
import Button from 'primevue/button';
import { RouterLink } from 'vue-router';
import StatusLabel from '../../../shared/ui/StatusLabel.vue';
import type { MatchPage } from '../api/listMatches';
import { companyWebsiteUrl } from '../lib/externalCompanyUrl';

defineProps<{
  page: MatchPage;
  offset: number;
  pageSize: number;
  fetching?: boolean;
}>();
const emit = defineEmits<{ previous: []; next: []; firstPage: [] }>();
</script>

<template>
  <section class="match-list" data-testid="match-list" :aria-busy="fetching ? 'true' : 'false'">
    <p class="list-context">Company fields show current public information.</p>
    <p v-if="fetching" role="status" class="refreshing">Refreshing matches…</p>
    <div class="match-list__table-wrap">
      <table class="match-list__table">
        <caption class="visually-hidden">
          Your company matches
        </caption>
        <thead>
          <tr>
            <th scope="col">Company</th>
            <th scope="col">Status</th>
            <th scope="col">Matched</th>
            <th scope="col">Country</th>
            <th scope="col">Sector</th>
            <th scope="col">Details</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="match in page.items" :key="match.id" data-testid="match-row">
            <td>
              <a
                v-if="companyWebsiteUrl(match.company.domain)"
                :href="companyWebsiteUrl(match.company.domain) ?? undefined"
                target="_blank"
                rel="noopener noreferrer"
                >{{ match.company.name }}</a
              >
              <span v-else>{{ match.company.name }}</span>
              <small>{{ match.company.domain }}</small>
            </td>
            <td><StatusLabel :status="match.status" /></td>
            <td>
              <time :datetime="match.created_at">{{
                new Date(match.created_at).toLocaleDateString()
              }}</time>
            </td>
            <td>{{ match.company.country ?? 'Not provided' }}</td>
            <td>{{ match.company.business_sector?.join(', ') || 'Not provided' }}</td>
            <td>
              <RouterLink :to="{ name: 'match-detail', params: { id: match.id } }"
                >View match</RouterLink
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <nav class="pagination" aria-label="Match pages">
      <Button
        label="Previous page"
        severity="secondary"
        :disabled="offset === 0 || fetching"
        @click="emit('previous')"
      />
      <span>Page {{ Math.floor(offset / pageSize) + 1 }}</span>
      <Button
        label="Next page"
        severity="secondary"
        :disabled="!page.has_more || fetching"
        @click="emit('next')"
      />
      <Button
        v-if="offset > 0"
        label="First page"
        severity="secondary"
        :disabled="fetching"
        @click="emit('firstPage')"
      />
    </nav>
  </section>
</template>

<style scoped>
.match-list {
  min-width: 0;
}
.match-list__table-wrap {
  max-width: 100%;
  overflow-x: auto;
}
.match-list__table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
  background: var(--color-surface);
}
th,
td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
td small {
  display: block;
  color: var(--color-text-muted);
}
a {
  color: var(--color-primary);
}
.pagination {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-top: var(--space-4);
}
.refreshing {
  color: var(--color-text-muted);
}
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
