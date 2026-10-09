<script setup lang="ts">
import EmptyState from '../../../shared/ui/EmptyState.vue';
import { RouterLink } from 'vue-router';
import type { MatchesOverview } from '../api/getMatchesOverview';

defineProps<{ overview: MatchesOverview | undefined; loading?: boolean }>();
</script>

<template>
  <EmptyState v-if="loading" message="Checking your latest match overview…" />
  <EmptyState
    v-else-if="overview && !overview.has_active_strategies"
    message="You have no matches yet. Add an active discovery strategy to start finding companies for your business."
    ><RouterLink to="/strategies">Manage discovery strategies</RouterLink></EmptyState
  >
  <EmptyState
    v-else-if="overview && overview.latest_evaluation === null"
    message="You have no matches yet. No managed evaluation is recorded for your active strategies."
  />
  <EmptyState
    v-else-if="
      overview?.latest_evaluation?.state === 'succeeded' &&
      !overview.latest_evaluation.tracking_stale &&
      overview.latest_evaluation.created_matches_count === 0
    "
    message="You have no matches yet. The latest completed evaluation created no new matches."
  />
  <EmptyState
    v-else
    message="You have no matches yet. Evaluation status is pending or unavailable."
  />
</template>
