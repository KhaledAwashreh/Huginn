<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import Button from 'primevue/button';
import Select from 'primevue/select';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import EmptyState from '../../../shared/ui/EmptyState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ProspectDetail from '../components/ProspectDetail.vue';
import ProspectList from '../components/ProspectList.vue';
import { PROSPECT_PAGE_SIZE, useProspectWorkspace } from '../composables/useProspectWorkspace';
import { useProspectCommands } from '../composables/useProspectCommands';
import type { ProspectCommandSubmission } from '../models/prospectCommandDraft';
import type { ProspectStage } from '../models/prospect';

const route = useRoute();
const router = useRouter();
const selectedId = computed(() => {
  const value = route.query.prospect_id;
  return typeof value === 'string' && value.trim() ? value : null;
});
const workspace = useProspectWorkspace(selectedId);
const commands = useProspectCommands(workspace.identity);
const selectedDraft = computed(() => {
  const prospect = workspace.detail.data.value;
  return prospect ? workspace.commandDraftFor(prospect.id, prospect) : null;
});
const statuses: { label: string; value: ProspectStage | 'all' }[] = [
  { label: 'All stages', value: 'all' },
  { label: 'Saved', value: 'saved' },
  { label: 'Contacted', value: 'contacted' },
  { label: 'In conversation', value: 'in_conversation' },
  { label: 'Proposal sent', value: 'proposal_sent' },
  { label: 'Won client', value: 'won_client' },
  { label: 'Closed', value: 'closed' },
];
const locked = computed(
  () =>
    commands.pending.value ||
    selectedDraft.value?.status === 'uncertain' ||
    selectedDraft.value?.status === 'stale',
);
const recoveryShelf = computed(() => workspace.recoveries.value);

function beforeUnload(event: BeforeUnloadEvent): void {
  if (!recoveryShelf.value.length) return;
  event.preventDefault();
  event.returnValue = '';
}
onBeforeRouteLeave(() => {
  if (!recoveryShelf.value.length) return true;
  return window.confirm(
    'Prospect drafts or unresolved commands are waiting. Leave this workspace?',
  );
});
onMounted(() => window.addEventListener('beforeunload', beforeUnload));
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload));

function routeForProspect(prospectId: string | null): void {
  const query = { ...route.query };
  if (prospectId) query.prospect_id = prospectId;
  else delete query.prospect_id;
  void router.replace({ query });
}
function previous(): void {
  workspace.setOffset(workspace.offset.value - PROSPECT_PAGE_SIZE);
}
function next(): void {
  if (workspace.prospects.data.value?.has_more)
    workspace.setOffset(workspace.offset.value + PROSPECT_PAGE_SIZE);
}
async function command(submission: ProspectCommandSubmission): Promise<void> {
  const draft = selectedDraft.value;
  if (!draft) return;
  await commands.submit(draft, submission);
}
function retryCurrent(): void {
  if (selectedDraft.value) void commands.retry(selectedDraft.value);
}
function refreshCurrent(): void {
  if (selectedId.value) void commands.refresh(selectedId.value);
}
function discardCurrent(): void {
  if (!selectedId.value) return;
  workspace.discardDraft(selectedId.value);
  void workspace.detail.refetch();
}
function retryDraft(prospectId: string): void {
  const draft = workspace.commandDraftFor(prospectId);
  void commands.retry(draft);
}
function refreshDraft(prospectId: string): void {
  void commands.refresh(prospectId);
}
function discardDraft(prospectId: string): void {
  workspace.discardDraft(prospectId);
}
function draftSummary(draft: NonNullable<typeof selectedDraft.value>): string {
  if (draft.status === 'uncertain') return 'The result is uncertain. Retry the original request.';
  if (draft.status === 'stale') return 'This draft is based on older prospect details.';
  if (draft.status === 'pending') return 'A prospect update is in progress.';
  return 'Unsaved prospect changes are retained here.';
}
</script>

<template>
  <div class="prospects-page">
    <PageHeader
      title="Prospects"
      description="Track saved companies with explicit stages, reminders and a retained activity history. Huginn does not contact companies for you."
    />

    <section class="prospect-workspace" aria-label="Saved prospects workspace">
      <aside class="collection-panel" aria-label="Prospect collection">
        <div class="collection-heading">
          <h2>Saved companies</h2>
          <label>
            <span>Search company name or domain</span>
            <input
              type="search"
              aria-label="Search prospects by company name or domain"
              placeholder="Search all prospects"
              :value="workspace.search.value"
              @input="workspace.search.value = ($event.target as HTMLInputElement).value"
            />
          </label>
          <label>
            <span>Prospect stage</span>
            <Select
              aria-label="Prospect stage"
              :model-value="workspace.stage.value"
              :options="statuses"
              option-label="label"
              option-value="value"
              @update:model-value="workspace.stage.value = $event"
            />
          </label>
          <p>Search applies across your Business prospects before the page is shown.</p>
        </div>
        <ProspectList
          :page="workspace.prospects.data.value"
          :selected-id="selectedId"
          :loading="workspace.prospects.isPending.value"
          :failed="workspace.prospects.isError.value"
          :fetching="workspace.prospects.isFetching.value"
          :offset="workspace.offset.value"
          :page-size="PROSPECT_PAGE_SIZE"
          @select="routeForProspect"
          @previous="previous"
          @next="next"
          @retry="workspace.prospects.refetch()"
        />
      </aside>

      <section class="detail-panel" aria-label="Selected prospect">
        <div
          v-if="recoveryShelf.length"
          class="recovery-shelf"
          aria-label="Prospect draft recovery"
        >
          <h2>Drafts and commands to recover</h2>
          <article
            v-for="recovery in recoveryShelf"
            :key="recovery.prospectId"
            class="recovery-item"
          >
            <div>
              <strong>{{ recovery.snapshot.company.name }}</strong>
              <p>{{ draftSummary(recovery.draft) }}</p>
            </div>
            <div class="recovery-actions">
              <Button
                label="Open retained prospect"
                severity="secondary"
                @click="routeForProspect(recovery.prospectId)"
              />
              <Button
                v-if="recovery.draft.status === 'uncertain'"
                label="Retry exact request"
                :disabled="commands.pending.value"
                @click="retryDraft(recovery.prospectId)"
              />
              <Button
                v-if="recovery.draft.status === 'stale'"
                label="Refresh current details"
                severity="secondary"
                :disabled="commands.pending.value"
                @click="refreshDraft(recovery.prospectId)"
              />
              <Button
                v-if="recovery.draft.status !== 'uncertain' && recovery.draft.status !== 'pending'"
                label="Discard draft"
                severity="secondary"
                @click="discardDraft(recovery.prospectId)"
              />
            </div>
          </article>
        </div>
        <LoadingState
          v-if="selectedId && workspace.detail.isPending.value"
          message="Loading prospect details…"
        />
        <ErrorState
          v-else-if="selectedId && workspace.detail.isError.value"
          message="Prospect details could not be loaded. The selected record may have changed or be unavailable to this Business."
        >
          <Button
            label="Retry prospect details"
            severity="secondary"
            @click="workspace.detail.refetch()"
          />
        </ErrorState>
        <ProspectDetail
          v-else-if="workspace.detail.data.value && selectedDraft"
          :prospect="workspace.detail.data.value"
          :draft="selectedDraft"
          :disabled="locked"
          :pending="commands.pending.value"
          :command-error="selectedDraft.error"
          :can-retry="selectedDraft.status === 'uncertain' && Boolean(selectedDraft.intent)"
          :needs-refresh="selectedDraft.status === 'stale'"
          :completion-message="
            commands.messageProspectId.value === selectedId ? commands.message.value : ''
          "
          @command="command"
          @retry="retryCurrent"
          @refresh="refreshCurrent"
          @discard-draft="discardCurrent"
        />
        <EmptyState
          v-else
          message="Select a saved prospect. Its assessment origin, current stage and retained history appear here."
        />
      </section>
    </section>
  </div>
</template>

<style scoped>
.prospects-page {
  display: grid;
  gap: var(--space-4);
}
.prospect-workspace {
  display: grid;
  grid-template-columns: minmax(15rem, 0.8fr) minmax(0, 1.7fr);
  gap: var(--space-5);
  align-items: start;
}
.collection-panel,
.detail-panel {
  display: grid;
  min-width: 0;
  gap: var(--space-4);
}
.collection-panel {
  position: sticky;
  top: var(--app-topbar-height, 5rem);
}
.collection-heading {
  display: grid;
  gap: var(--space-3);
}
.collection-heading h2,
.recovery-shelf h2 {
  margin: 0;
  font-size: 1.1rem;
}
.collection-heading label {
  display: grid;
  gap: var(--space-1);
}
.collection-heading input {
  min-height: 42px;
  width: 100%;
  min-width: 0;
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
}
.collection-heading p {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.9rem;
}
.recovery-shelf {
  display: grid;
  gap: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  padding: var(--space-3);
  background: var(--color-surface-muted);
}
.recovery-item {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-2);
}
.recovery-item p {
  margin: var(--space-1) 0 0;
  color: var(--color-text-muted);
}
.recovery-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
@media (max-width: 800px) {
  .prospect-workspace {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
  }
  .collection-panel {
    position: static;
    border-bottom: 1px solid var(--color-border);
    padding-bottom: var(--space-4);
  }
}
</style>
