<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, RouterLink } from 'vue-router';
import Button from 'primevue/button';
import { ApiError } from '../../../api/apiError';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import StatusLabel from '../../../shared/ui/StatusLabel.vue';
import MatchSignals from '../components/MatchSignals.vue';
import { useMatch } from '../composables/useMatch';
import { useMatchSignals } from '../composables/useMatchSignals';
import { companyWebsiteUrl } from '../lib/externalCompanyUrl';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const { query: match } = useMatch(id);
const signalState = useMatchSignals(id);

function canRetry(error: unknown): boolean {
  return (
    !(error instanceof ApiError) ||
    error.status >= 500 ||
    error.status === 429 ||
    error.status === 408
  );
}
</script>

<template>
  <div class="match-detail">
    <PageHeader
      :title="match.data.value?.company.name ?? 'Match details'"
      description="Review the stored match and the company’s current public context."
    >
      <RouterLink to="/matches">Back to matches</RouterLink>
    </PageHeader>
    <LoadingState
      v-if="match.isPending.value && !match.data.value"
      message="Loading match details…"
    />
    <ErrorState
      v-else-if="match.isError.value && !match.data.value"
      message="This match could not be loaded."
    >
      <Button
        v-if="canRetry(match.error.value)"
        label="Retry match"
        :disabled="match.isFetching.value"
        @click="match.refetch()"
      />
      <RouterLink to="/matches">Back to matches</RouterLink>
    </ErrorState>
    <template v-else-if="match.data.value">
      <ErrorState
        v-if="match.isError.value"
        message="Match details could not be refreshed. Showing the last received details."
      >
        <Button
          v-if="canRetry(match.error.value)"
          label="Retry match"
          :disabled="match.isFetching.value"
          @click="match.refetch()"
        />
      </ErrorState>
      <section class="match-summary" aria-labelledby="match-summary-heading">
        <div class="section-title">
          <h2 id="match-summary-heading">Match record</h2>
          <StatusLabel :status="match.data.value.status" />
        </div>
        <dl class="summary-grid">
          <div>
            <dt>Match ID</dt>
            <dd>
              <code>{{ match.data.value.id }}</code>
            </dd>
          </div>
          <div>
            <dt>Matched</dt>
            <dd>
              <time :datetime="match.data.value.created_at">{{
                new Date(match.data.value.created_at).toLocaleString()
              }}</time>
            </dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>
              <time :datetime="match.data.value.updated_at">{{
                new Date(match.data.value.updated_at).toLocaleString()
              }}</time>
            </dd>
          </div>
          <div class="notes">
            <dt>Stored notes</dt>
            <dd>{{ match.data.value.notes || 'No notes were recorded.' }}</dd>
          </div>
        </dl>
      </section>
      <section class="company-context" aria-labelledby="company-context-heading">
        <div class="section-title">
          <div>
            <h2 id="company-context-heading">Current company context</h2>
            <p>
              These are current company attributes. They do not explain why this match was created.
            </p>
          </div>
        </div>
        <dl class="summary-grid">
          <div>
            <dt>Company</dt>
            <dd>{{ match.data.value.company.name }}</dd>
          </div>
          <div>
            <dt>Website</dt>
            <dd>
              <a
                v-if="companyWebsiteUrl(match.data.value.company.domain)"
                :href="companyWebsiteUrl(match.data.value.company.domain) ?? undefined"
                target="_blank"
                rel="noopener noreferrer"
                >{{ match.data.value.company.domain }}</a
              ><span v-else>{{ match.data.value.company.domain }}</span>
            </dd>
          </div>
          <div>
            <dt>Business sectors</dt>
            <dd>{{ match.data.value.company.business_sector?.join(', ') || 'Not provided' }}</dd>
          </div>
          <div>
            <dt>Country</dt>
            <dd>{{ match.data.value.company.country || 'Not provided' }}</dd>
          </div>
          <div>
            <dt>Company scale</dt>
            <dd>{{ match.data.value.company.company_scale || 'Not provided' }}</dd>
          </div>
          <div>
            <dt>Company status</dt>
            <dd>{{ match.data.value.company.company_status || 'Not provided' }}</dd>
          </div>
        </dl>
      </section>
      <MatchSignals
        :page="signalState.signals.data.value"
        :offset="signalState.offset.value"
        :page-size="signalState.pageSize"
        :pending="signalState.signals.isPending.value"
        :fetching="signalState.signals.isFetching.value"
        :failed="signalState.signals.isError.value"
        :error="signalState.signals.error.value"
        @previous="signalState.previousPage"
        @next="signalState.nextPage"
        @retry="signalState.signals.refetch()"
      />
    </template>
  </div>
</template>

<style scoped>
.match-detail {
  display: grid;
  gap: var(--space-6);
  min-width: 0;
}
.match-summary,
.company-context {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
.section-title {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  justify-content: space-between;
  flex-wrap: wrap;
}
h2 {
  margin: 0;
  font-size: 1.2rem;
}
.section-title p {
  margin: var(--space-2) 0 0;
  color: var(--color-text-muted);
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: var(--space-4);
  margin: 0;
}
.summary-grid div {
  min-width: 0;
}
dt {
  color: var(--color-text-muted);
  font-size: 0.9rem;
}
dd {
  margin: var(--space-1) 0 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.notes {
  grid-column: 1 / -1;
}
code {
  overflow-wrap: anywhere;
}
a {
  color: var(--color-primary);
}
</style>
