<script setup lang="ts">
import { computed, ref } from 'vue';
import { Search } from '@lucide/vue';
import Button from 'primevue/button';
import { ApiError } from '../../../api/apiError';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import MatchGrid from '../components/MatchGrid.vue';
import MatchPagination from '../components/MatchPagination.vue';
import MatchOverviewEmptyState from '../components/MatchOverviewEmptyState.vue';
import { useMatches } from '../composables/useMatches';
import { useMatchesOverview } from '../composables/useMatchesOverview';

const list = useMatches();
const { overview } = useMatchesOverview();
const search = ref('');
const visibleMatches = computed(() => {
  const items = list.matches.data.value?.items ?? [];
  const query = search.value.trim().toLocaleLowerCase();
  if (!query) return items;
  return items.filter(({ company }) =>
    [company.name, company.domain, company.country, ...(company.business_sector ?? [])]
      .join(' ')
      .toLocaleLowerCase()
      .includes(query),
  );
});

function canRetry(error: unknown): boolean {
  return (
    !(error instanceof ApiError) ||
    error.status >= 500 ||
    error.status === 429 ||
    error.status === 408
  );
}

function firstPage(): void {
  list.setOffset(0);
}
</script>

<template>
  <div class="matches-page">
    <PageHeader title="Matches" />
    <section class="matches-workspace" aria-label="Matched companies">
      <div v-if="list.matches.data.value?.items.length" class="match-search">
        <Search :size="18" aria-hidden="true" />
        <input
          v-model="search"
          type="search"
          aria-label="Search matches"
          placeholder="Search matches"
        />
      </div>
      <ErrorState
        v-if="overview.isError.value"
        :message="
          list.matches.data.value
            ? 'Evaluation context could not be loaded. Your match list remains visible.'
            : 'Evaluation context could not be loaded.'
        "
      >
        <Button
          v-if="canRetry(overview.error.value)"
          label="Retry overview"
          :disabled="overview.isFetching.value"
          @click="overview.refetch()"
        />
      </ErrorState>
      <LoadingState
        v-if="list.matches.isPending.value && !list.matches.data.value"
        message="Loading your matches…"
      />
      <ErrorState
        v-else-if="list.matches.isError.value && !list.matches.data.value"
        message="Your matches could not be loaded."
      >
        <Button
          v-if="canRetry(list.matches.error.value)"
          label="Retry matches"
          :disabled="list.matches.isFetching.value"
          @click="list.matches.refetch()"
        />
      </ErrorState>
      <template v-else-if="list.matches.data.value">
        <ErrorState
          v-if="list.matches.isError.value"
          message="Matches could not be refreshed. Showing the last received page."
        >
          <Button
            v-if="canRetry(list.matches.error.value)"
            label="Retry matches"
            :disabled="list.matches.isFetching.value"
            @click="list.matches.refetch()"
          />
        </ErrorState>
        <EmptyState
          v-if="list.matches.data.value.items.length && !visibleMatches.length"
          message="No matches on this page fit your search. Search covers only the current page."
        />
        <MatchGrid
          v-else-if="list.matches.data.value.items.length"
          :items="visibleMatches"
          :fetching="list.matches.isFetching.value"
        />
        <template v-else-if="list.offset.value > 0 || overview.data.value?.has_matches">
          <EmptyState message="This page has no matches. Return to the first page or refresh." />
          <div class="empty-actions">
            <Button
              v-if="list.offset.value > 0"
              label="First page"
              severity="secondary"
              @click="firstPage"
            />
            <Button
              v-if="list.offset.value === 0"
              label="Refresh matches"
              severity="secondary"
              :disabled="list.matches.isFetching.value"
              @click="list.matches.refetch()"
            />
          </div>
        </template>
        <template v-else>
          <EmptyState
            v-if="overview.isError.value"
            message="No matches appear on the first page. Evaluation context is unavailable."
          />
          <MatchOverviewEmptyState
            v-else
            :overview="overview.data.value"
            :loading="overview.isPending.value"
          />
        </template>
        <MatchPagination
          v-if="list.matches.data.value.items.length"
          :has-more="list.matches.data.value.has_more"
          :offset="list.offset.value"
          :page-size="list.pageSize"
          :fetching="list.matches.isFetching.value"
          @previous="list.previousPage"
          @next="list.nextPage"
          @first-page="firstPage"
        />
      </template>
    </section>
  </div>
</template>

<style scoped>
.matches-page,
.matches-workspace {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}
.match-search {
  max-width: 24rem;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text-muted);
}
.match-search:focus-within {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
.match-search input {
  min-width: 0;
  min-height: 42px;
  flex: 1;
  border: 0;
  outline: 0;
  box-shadow: none;
  background: transparent;
  color: var(--color-text);
}
.empty-actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}
</style>
