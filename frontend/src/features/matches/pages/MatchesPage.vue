<script setup lang="ts">
import Button from 'primevue/button';
import { ApiError } from '../../../api/apiError';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import MatchList from '../components/MatchList.vue';
import MatchOverviewEmptyState from '../components/MatchOverviewEmptyState.vue';
import MatchStatusFilter from '../components/MatchStatusFilter.vue';
import { useMatches } from '../composables/useMatches';
import { useMatchesOverview } from '../composables/useMatchesOverview';

const list = useMatches();
const { overview } = useMatchesOverview();

function canRetry(error: unknown): boolean {
  return (
    !(error instanceof ApiError) ||
    error.status >= 500 ||
    error.status === 429 ||
    error.status === 408
  );
}

function clearFilter(): void {
  list.setStatus(undefined);
}
function firstPage(): void {
  list.setOffset(0);
}
</script>

<template>
  <div class="matches-page">
    <PageHeader title="Matches" description="Browse your recorded company matches." />
    <section class="matches-workspace" aria-labelledby="matches-heading">
      <div class="matches-toolbar">
        <h2 id="matches-heading">Your matches</h2>
        <MatchStatusFilter :model-value="list.status.value" @update:model-value="list.setStatus" />
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
        <MatchList
          v-if="list.matches.data.value.items.length"
          :page="list.matches.data.value"
          :offset="list.offset.value"
          :page-size="list.pageSize"
          :fetching="list.matches.isFetching.value"
          @previous="list.previousPage"
          @next="list.nextPage"
          @first-page="firstPage"
        />
        <template
          v-else-if="list.status.value || list.offset.value > 0 || overview.data.value?.has_matches"
        >
          <EmptyState
            :message="
              list.status.value
                ? 'No matches are on this page for the selected status.'
                : 'This page has no matches. Return to the first page or refresh.'
            "
          />
          <div class="empty-actions">
            <Button
              v-if="list.status.value"
              label="Clear filter"
              severity="secondary"
              @click="clearFilter"
            />
            <Button
              v-if="list.offset.value > 0"
              label="First page"
              severity="secondary"
              @click="firstPage"
            />
            <Button
              v-if="!list.status.value && list.offset.value === 0"
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
      </template>
    </section>
  </div>
</template>

<style scoped>
.matches-page {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}
.matches-workspace {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}
.matches-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-wrap: wrap;
  justify-content: space-between;
}
h2 {
  margin: 0;
  font-size: 1.2rem;
}
.empty-actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}
</style>
