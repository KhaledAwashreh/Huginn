<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import Button from 'primevue/button';
import Select from 'primevue/select';
import { onBeforeRouteLeave, RouterLink, useRoute } from 'vue-router';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import { useRecommendationWorkspace } from '../composables/useRecommendationWorkspace';
import RecommendationEvidence from '../components/RecommendationEvidence.vue';
import RecommendationCommandActions from '../components/RecommendationCommandActions.vue';
import SuppressionManagement from '../components/SuppressionManagement.vue';
import RecommendationQualityFeedback from '../components/RecommendationQualityFeedback.vue';
import LinkedRecommendation from '../components/LinkedRecommendation.vue';
import RecommendationPresentation from '../components/RecommendationPresentation.vue';
import type { components } from '../../../api/generated/schema';
type RecommendationResponse = components['schemas']['RecommendationResponse'];

const workspace = useRecommendationWorkspace();
const route = useRoute();
const emailLink = computed(() => {
  const recommendationId = route?.query.recommendation_id;
  const assessmentRevisionId = route?.query.assessment_revision_id;
  return typeof recommendationId === 'string' &&
    typeof assessmentRevisionId === 'string' &&
    recommendationId &&
    assessmentRevisionId
    ? { recommendationId, assessmentRevisionId }
    : null;
});
const linkedAvailable = ref(false);
const queryRecommendationIds = computed(() => {
  const ids = new Set(
    workspace.recommendations.data.value?.items
      .filter((item) => item.id !== emailLink.value?.recommendationId)
      .map((item) => item.id) ?? [],
  );
  if (emailLink.value && linkedAvailable.value) ids.add(emailLink.value.recommendationId);
  return ids;
});
const recoveryShelf = computed(() =>
  workspace.commandRecoveries.value.filter(
    (recovery) => !queryRecommendationIds.value.has(recovery.recommendationId),
  ),
);
function beforeUnload(event: BeforeUnloadEvent): void {
  if (!workspace.commandRecoveries.value.length) return;
  event.preventDefault();
  event.returnValue = '';
}
onBeforeRouteLeave(() => {
  if (!workspace.commandRecoveries.value.length) return true;
  return window.confirm(
    'Recommendation drafts or unresolved reports are waiting in the recovery list. Leave this workspace?',
  );
});
onMounted(() => window.addEventListener('beforeunload', beforeUnload));
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload));
const notice = ref('');
const statuses = [
  { label: 'Open recommendations', value: 'open' },
  { label: 'Converted to prospects', value: 'converted' },
  { label: 'Not relevant', value: 'rejected' },
  { label: 'All recommendations', value: 'all' },
];
function completed(event: { kind: string; message: string }): void {
  notice.value = event.message;
}
async function generate(): Promise<void> {
  notice.value = '';
  if (await workspace.generate(workspace.strategyId.value)) {
    notice.value = 'Recommendations refreshed.';
  }
}
function pagePrevious(): void {
  workspace.setOffset(workspace.offset.value - 25);
}
function pageNext(): void {
  if (workspace.recommendations.data.value?.has_more)
    workspace.setOffset(workspace.offset.value + 25);
}
function statusLabel(item: RecommendationResponse): string {
  return item.status === 'open'
    ? 'Open'
    : item.status === 'converted'
      ? 'Saved as prospect'
      : 'Not relevant';
}
</script>

<template>
  <div class="recommendations-page">
    <PageHeader
      title="Recommendations"
      description="Find companies worth a closer look. Open a card for company info and signals."
    />
    <p class="guidance">
      A fit assessment does not establish buying intent. Confirm the company’s needs and buying role
      before outreach. Huginn does not contact companies for you.
    </p>

    <LinkedRecommendation
      v-if="emailLink"
      :recommendation-id="emailLink.recommendationId"
      :assessment-revision-id="emailLink.assessmentRevisionId"
      :identity="workspace.identity.value"
      :draft-state="workspace.commandDraftFor(emailLink.recommendationId)"
      :preferences="workspace.preferences.data.value ?? null"
      :preferences-loading="workspace.preferences.isPending.value"
      :preferences-failed="workspace.preferences.isError.value"
      :refresh-preferences="workspace.refreshPreferences"
      @completed="completed"
      @available="linkedAvailable = $event"
    />

    <section
      v-if="recoveryShelf.length"
      class="recovery-shelf"
      aria-label="Recommendation drafts awaiting recovery"
    >
      <div>
        <h2>Drafts and uncertain reports</h2>
        <p>
          These items stay available while you search, filter, paginate, or return to this
          workspace. Uncertain commands can only be retried with their original request.
        </p>
      </div>
      <article v-for="recovery in recoveryShelf" :key="recovery.recommendationId">
        <RecommendationEvidence :recommendation="recovery.snapshot" />
        <RecommendationQualityFeedback
          v-if="recovery.feedbackDraft && recovery.snapshot.assessment"
          :recommendation="recovery.snapshot"
          :identity="workspace.identity.value"
          :draft-state="recovery.draft"
        />
        <RecommendationCommandActions
          v-if="recovery.decisionDraft && recovery.snapshot.status === 'open'"
          :recommendation="recovery.snapshot"
          :draft-state="recovery.draft"
          :preferences="workspace.preferences.data.value ?? null"
          :preferences-loading="workspace.preferences.isPending.value"
          :preferences-failed="workspace.preferences.isError.value"
          :identity="workspace.identity.value"
          :refresh-preferences="workspace.refreshPreferences"
          @completed="completed"
        />
      </article>
    </section>

    <section class="toolbar" aria-label="Recommendation search and filters">
      <label class="search-field">
        <span>Search company name or domain</span>
        <input
          type="search"
          aria-label="Search recommendations by company name or domain"
          placeholder="Search all recommendations"
          :value="workspace.search.value"
          @input="workspace.search.value = ($event.target as HTMLInputElement).value"
        />
      </label>
      <div class="filter-field">
        <label for="recommendation-status">Recommendation status</label>
        <Select
          input-id="recommendation-status"
          aria-label="Recommendation status"
          :model-value="workspace.status.value"
          :options="statuses"
          option-label="label"
          option-value="value"
          @update:model-value="workspace.status.value = $event"
        />
      </div>
    </section>
    <p class="search-help">Search your recommendations by company name or domain.</p>

    <section class="generation" aria-label="Generate recommendations">
      <Button
        :label="workspace.generating.value ? 'Generating…' : 'Generate recommendations'"
        :disabled="
          !workspace.strategyId.value ||
          workspace.generating.value ||
          workspace.strategies.isError.value
        "
        @click="generate"
      />
      <p v-if="workspace.strategies.isError.value" class="error-inline" role="alert">
        Your recommendation setup could not be loaded.
        <Button label="Retry profile" text @click="workspace.strategies.refetch()" />
      </p>
      <LoadingState
        v-else-if="workspace.strategies.isPending.value"
        message="Loading your profile…"
      />
      <p v-else-if="workspace.configurationConflict.value" class="error-inline" role="alert">
        Multiple recommendation setups are active for your business. Contact support to resolve this
        configuration conflict.
      </p>
      <p v-else-if="!workspace.strategyId.value" class="search-help">
        Add your service and ideal clients to start finding recommendations.
        <RouterLink to="/profile">Complete your profile</RouterLink>.
      </p>
      <p v-if="workspace.generationError.value" class="error-inline" role="alert">
        {{ workspace.generationError.value }}
      </p>
    </section>

    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <ErrorState
      v-if="workspace.preferences.isError.value"
      message="Business repeat timing could not be loaded. Later decisions are unavailable until it refreshes."
    >
      <Button
        label="Retry repeat timing"
        severity="secondary"
        @click="workspace.preferences.refetch()"
      />
    </ErrorState>
    <template v-if="!workspace.strategyId.value">
      <EmptyState
        v-if="
          !workspace.strategies.isPending.value &&
          !workspace.strategies.isError.value &&
          !workspace.configurationConflict.value
        "
        message="Complete your profile to view recommendations."
      />
    </template>
    <LoadingState
      v-else-if="workspace.recommendations.isPending.value && !workspace.recommendations.data.value"
      message="Loading Business recommendations…"
    />
    <ErrorState
      v-else-if="workspace.recommendations.isError.value && !workspace.recommendations.data.value"
      message="Recommendations could not be loaded."
    >
      <Button
        label="Retry recommendations"
        severity="secondary"
        @click="workspace.recommendations.refetch()"
      />
    </ErrorState>
    <template v-else-if="workspace.recommendations.data.value">
      <ErrorState
        v-if="workspace.recommendations.isError.value"
        message="Recommendations could not be refreshed. Showing the last received page."
      >
        <Button
          label="Retry recommendations"
          severity="secondary"
          @click="workspace.recommendations.refetch()"
        />
      </ErrorState>
      <LoadingState
        v-if="
          workspace.recommendations.isFetching.value &&
          !workspace.recommendations.data.value.items.length
        "
        message="Refreshing recommendations…"
      />
      <EmptyState
        v-else-if="!workspace.recommendations.data.value.items.length"
        :message="
          workspace.offset.value
            ? 'No recommendations appear on this page.'
            : 'No recommendations match this view yet.'
        "
      />
      <ol
        v-else
        class="recommendation-list"
        :aria-busy="workspace.recommendations.isFetching.value"
      >
        <template v-for="row in workspace.recommendations.data.value.items" :key="row.id">
          <li v-if="row.id !== emailLink?.recommendationId">
            <article class="recommendation-card">
              <RecommendationPresentation
                v-slot="{ recommendation: item }"
                :recommendation="row"
                :identity="workspace.identity.value"
                @confirmed="workspace.refresh()"
              >
                <div v-if="item.status !== 'open'" class="card-heading">
                  <span class="status">{{ statusLabel(item) }}</span>
                </div>
                <RecommendationEvidence
                  :recommendation="item"
                  :strategy-id="workspace.strategyId.value"
                />
                <p v-if="item.prospect" class="saved-link">
                  <RouterLink :to="{ path: '/prospects', query: { prospect_id: item.prospect.id } }"
                    >View prospect</RouterLink
                  >
                  ·
                  {{ item.prospect.stage.replaceAll('_', ' ') }}
                </p>
                <p v-if="item.status !== 'open'" class="resolved-note">
                  This recommendation is resolved. Its assessment and history remain available; no
                  further decision can be applied here.
                </p>
                <RecommendationCommandActions
                  v-if="item.status === 'open'"
                  :recommendation="item"
                  :draft-state="workspace.commandDraftFor(item.id)"
                  :preferences="workspace.preferences.data.value ?? null"
                  :preferences-loading="workspace.preferences.isPending.value"
                  :preferences-failed="workspace.preferences.isError.value"
                  :identity="workspace.identity.value"
                  :refresh-preferences="workspace.refreshPreferences"
                  @completed="completed"
                />
                <RecommendationQualityFeedback
                  v-if="
                    item.assessment &&
                    (workspace.commandDraftFor(item.id).laterConfirmationOpen ||
                      workspace.commandDraftFor(item.id).feedback.intent ||
                      workspace.commandDraftFor(item.id).feedback.status === 'error')
                  "
                  :recommendation="item"
                  :identity="workspace.identity.value"
                  :draft-state="workspace.commandDraftFor(item.id)"
                />
              </RecommendationPresentation>
            </article>
          </li>
        </template>
      </ol>
      <nav
        v-if="workspace.recommendations.data.value.items.length || workspace.offset.value"
        class="pagination"
        aria-label="Recommendation pages"
      >
        <Button
          label="Previous"
          severity="secondary"
          :disabled="workspace.offset.value === 0 || workspace.recommendations.isFetching.value"
          @click="pagePrevious"
        />
        <span
          >Showing {{ workspace.offset.value + 1 }}–{{
            workspace.offset.value + workspace.recommendations.data.value.items.length
          }}</span
        >
        <Button
          label="Next"
          severity="secondary"
          :disabled="
            !workspace.recommendations.data.value.has_more ||
            workspace.recommendations.isFetching.value
          "
          @click="pageNext"
        />
      </nav>
    </template>

    <section class="suppression-section">
      <Button
        :label="workspace.suppressionsVisible.value ? 'Hide suppressions' : 'Manage suppressions'"
        severity="secondary"
        aria-controls="suppression-manager"
        :aria-expanded="workspace.suppressionsVisible.value"
        @click="workspace.suppressionsVisible.value = !workspace.suppressionsVisible.value"
      />
      <SuppressionManagement
        v-if="workspace.suppressionsVisible.value"
        id="suppression-manager"
        :identity="workspace.identity.value"
        :page="workspace.suppressions.data.value"
        :pending="workspace.suppressions.isPending.value"
        :failed="workspace.suppressions.isError.value"
        :fetching="workspace.suppressions.isFetching.value"
        :search="workspace.suppressionSearch.value"
        :offset="workspace.suppressionOffset.value"
        :page-size="25"
        @search="workspace.suppressionSearch.value = $event"
        @next="workspace.setSuppressionOffset(workspace.suppressionOffset.value + 25)"
        @previous="workspace.setSuppressionOffset(workspace.suppressionOffset.value - 25)"
        @refresh="workspace.refresh()"
      />
    </section>
  </div>
</template>

<style scoped>
.recommendations-page {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}
.recovery-shelf {
  display: grid;
  gap: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  background: var(--color-surface-muted);
}
.recovery-shelf > div > h2,
.recovery-shelf > div > p {
  margin: 0;
}
.recovery-shelf > article {
  display: grid;
  gap: var(--space-4);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-4);
}
.guidance,
.search-help,
.resolved-note {
  margin: 0;
  color: var(--color-text-muted);
}
.toolbar {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  align-items: end;
}
.search-field,
.filter-field,
.field {
  display: grid;
  gap: var(--space-1);
}
.search-field {
  flex: 1 1 20rem;
}
.search-field input {
  min-height: 42px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
}
.search-field input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
.filter-field {
  flex: 0 1 18rem;
}
label {
  font-weight: 600;
}
.generation {
  display: flex;
  gap: var(--space-3);
  align-items: end;
  flex-wrap: wrap;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
}
.generation .field {
  min-width: min(100%, 19rem);
}
.generation .error-inline {
  flex-basis: 100%;
}
.recommendation-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--space-4);
}
.recommendation-card {
  display: grid;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
.card-heading {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  flex-wrap: wrap;
  justify-content: space-between;
}
.card-heading,
.saved-link,
.resolved-note {
  margin: var(--space-3) var(--space-5);
}
.status {
  border-radius: 999px;
  border: 1px solid var(--color-border);
  padding: 0.2rem 0.6rem;
  font-size: 0.875rem;
}
code {
  overflow-wrap: anywhere;
}
.saved-link,
.notice {
  margin: 0;
}
.error-inline {
  margin: 0;
  color: var(--color-danger, #a12b32);
}
.pagination {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
}
.suppression-section {
  display: grid;
  gap: var(--space-3);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-4);
}
</style>
