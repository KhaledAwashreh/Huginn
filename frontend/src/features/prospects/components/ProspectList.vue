<script setup lang="ts">
import Button from 'primevue/button';
import type { ProspectPage, ProspectView } from '../models/prospect';
import { activeStageLabel } from '../models/prospect';
import { followUpStatus } from '../models/followUpStatus';
import { useProspectClock } from '../composables/useProspectClock';

defineProps<{
  page: ProspectPage | undefined;
  selectedId: string | null;
  loading: boolean;
  failed: boolean;
  fetching: boolean;
  offset: number;
  pageSize: number;
}>();
const emit = defineEmits<{ select: [prospectId: string]; previous: []; next: []; retry: [] }>();
const now = useProspectClock();

function followUp(prospect: ProspectView): string {
  const followUpAt = prospect.follow_up_at;
  if (!followUpAt) return 'No reminder';
  const status = followUpStatus(followUpAt, now.value);
  const label = status === 'due' ? 'Due' : 'Upcoming';
  return `${label} · Reminder ${new Date(followUpAt).toLocaleDateString()}`;
}
</script>

<template>
  <section class="prospect-list" aria-label="Saved prospects" :aria-busy="fetching">
    <p v-if="loading && !page" role="status">Loading prospects…</p>
    <div v-else-if="failed && !page" class="error-state">
      <p>Prospects could not be loaded.</p>
      <Button label="Retry prospects" severity="secondary" @click="emit('retry')" />
    </div>
    <p v-else-if="page && !page.items.length">No prospects match this view.</p>
    <ul v-else-if="page" class="items">
      <li v-for="prospect in page.items" :key="prospect.id">
        <button
          type="button"
          class="prospect-choice"
          :aria-current="selectedId === prospect.id ? 'page' : undefined"
          :aria-label="`Open prospect ${prospect.company.name}`"
          @click="emit('select', prospect.id)"
        >
          <span class="name">{{ prospect.company.name }}</span>
          <span class="domain">{{ prospect.company.domain }}</span>
          <span class="state">
            <span class="stage">{{ activeStageLabel(prospect.stage) }}</span>
            <span>{{ followUp(prospect) }}</span>
          </span>
        </button>
      </li>
    </ul>
    <nav v-if="page" class="pagination" aria-label="Prospect pages">
      <Button
        label="Previous"
        severity="secondary"
        :disabled="offset === 0 || fetching"
        @click="emit('previous')"
      />
      <span>Showing {{ offset + 1 }}–{{ offset + page.items.length }}</span>
      <Button
        label="Next"
        severity="secondary"
        :disabled="!page.has_more || fetching"
        @click="emit('next')"
      />
    </nav>
  </section>
</template>

<style scoped>
.prospect-list {
  display: grid;
  gap: var(--space-3);
  min-width: 0;
}
.items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.items li {
  border-top: 1px solid var(--color-border);
}
.prospect-choice {
  display: grid;
  width: 100%;
  min-height: 72px;
  gap: var(--space-1);
  padding: var(--space-3);
  border: 0;
  border-inline-start: 3px solid transparent;
  background: transparent;
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
}
.prospect-choice:hover,
.prospect-choice[aria-current='page'] {
  background: var(--color-surface-muted);
}
.prospect-choice[aria-current='page'] {
  border-inline-start-color: var(--color-primary);
}
.name {
  font-weight: 650;
  overflow-wrap: anywhere;
}
.domain,
.state {
  color: var(--color-text-muted);
  font-size: 0.9rem;
  overflow-wrap: anywhere;
}
.state {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.stage {
  color: var(--color-text);
  text-transform: capitalize;
}
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-2);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-3);
}
.error-state {
  display: grid;
  justify-items: start;
  gap: var(--space-2);
}
</style>
