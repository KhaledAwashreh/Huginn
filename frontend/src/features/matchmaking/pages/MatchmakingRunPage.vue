<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import Button from 'primevue/button';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import { useSession } from '../../session/composables/useSession';
import { useMatchmakingRun } from '../composables/useMatchmakingRun';
import { validateMatchmakingRunId } from '../navigation/validateMatchmakingQuery';
import MatchmakingProgress from '../components/MatchmakingProgress.vue';
import UserResultTable from '../components/UserResultTable.vue';
const route = useRoute();
const session = useSession();
const runId = computed(() => String(route.params.id ?? ''));
const validId = computed(() => validateMatchmakingRunId(runId.value));
const offset = ref(0);
const detail = useMatchmakingRun(
  () => (validId.value ? runId.value : ''),
  () => offset.value,
);
watch(runId, () => {
  offset.value = 0;
});
</script>

<template>
  <PageHeader
    title="Matchmaking run"
    description="Inspect captured scope, signal window, execution progress, and per-user results."
    ><RouterLink to="/admin/matchmaking">Back to matchmaking history</RouterLink></PageHeader
  >
  <section v-if="!session.isAdministrator.value" class="forbidden" role="alert">
    <h2>Administrator access required</h2>
    <p>Your session cannot view this run.</p>
  </section>
  <ErrorState v-else-if="!validId" message="This run link does not contain a valid ID." />
  <LoadingState v-else-if="detail.run.isPending.value" message="Loading matchmaking run…" />
  <ErrorState
    v-else-if="detail.run.isError.value && !detail.run.data.value"
    message="Matchmaking run details could not be loaded."
    ><Button
      label="Retry details"
      :disabled="detail.run.isFetching.value"
      @click="detail.run.refetch()"
  /></ErrorState>
  <template v-else-if="detail.run.data.value">
    <p v-if="detail.run.isFetching.value" role="status">Refreshing the last known run state…</p>
    <p v-if="detail.run.isError.value" role="alert">
      Refresh failed. Showing the last received run state from
      {{ new Date(detail.run.dataUpdatedAt.value).toLocaleString() }}.
    </p>
    <section class="scope">
      <h2>Accepted run scope</h2>
      <dl>
        <div>
          <dt>Run ID</dt>
          <dd>
            <code>{{ detail.run.data.value.id }}</code>
          </dd>
        </div>
        <div>
          <dt>Target scope</dt>
          <dd>{{ detail.run.data.value.target_kind.replaceAll('_', ' ') }}</dd>
        </div>
        <div>
          <dt>Requester account</dt>
          <dd>
            <code>{{ detail.run.data.value.requester_account_id }}</code>
          </dd>
        </div>
        <div>
          <dt>Signal start</dt>
          <dd>
            {{ new Date(detail.run.data.value.cutoff).toLocaleString() }} ({{
              detail.run.data.value.cutoff
            }})
          </dd>
        </div>
        <div>
          <dt>Signal end</dt>
          <dd>
            {{ new Date(detail.run.data.value.as_of).toLocaleString() }} ({{
              detail.run.data.value.as_of
            }})
          </dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd :title="detail.run.data.value.started_at ?? undefined">
            {{
              detail.run.data.value.started_at
                ? new Date(detail.run.data.value.started_at).toLocaleString()
                : 'Not started'
            }}
          </dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd :title="detail.run.data.value.finished_at ?? undefined">
            {{
              detail.run.data.value.finished_at
                ? new Date(detail.run.data.value.finished_at).toLocaleString()
                : 'Not finished'
            }}
          </dd>
        </div>
        <div>
          <dt>Last tracking update</dt>
          <dd :title="detail.run.data.value.heartbeat_at ?? undefined">
            {{
              detail.run.data.value.heartbeat_at
                ? new Date(detail.run.data.value.heartbeat_at).toLocaleString()
                : 'No heartbeat recorded'
            }}
          </dd>
        </div>
        <div>
          <dt>Requested</dt>
          <dd>{{ new Date(detail.run.data.value.requested_at).toLocaleString() }}</dd>
        </div>
      </dl>
    </section>
    <MatchmakingProgress :run="detail.run.data.value" />
    <UserResultTable
      :run-id="runId"
      :items="detail.results.data.value?.items ?? []"
      :has-more="detail.results.data.value?.has_more ?? false"
      :offset="offset"
      :page-size="detail.pageSize"
      :state="detail.state.value"
      @update:offset="offset = $event"
      @update:state="
        detail.state.value = $event;
        offset = 0;
      "
    />
    <p v-if="detail.results.isError.value" role="alert">
      User outcomes could not be refreshed. The last received page remains visible.
      <Button
        label="Retry user outcomes"
        :disabled="detail.results.isFetching.value"
        @click="detail.results.refetch()"
      />
    </p>
    <p v-if="detail.results.isFetching.value" role="status">Refreshing user outcomes…</p>
  </template>
</template>

<style scoped>
.scope {
  margin-block: var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
}
.scope dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: var(--space-3);
}
.scope dt {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
.scope dd {
  margin: 0.25rem 0 0;
  overflow-wrap: anywhere;
}
.forbidden {
  padding: var(--space-4);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-card);
}
</style>
