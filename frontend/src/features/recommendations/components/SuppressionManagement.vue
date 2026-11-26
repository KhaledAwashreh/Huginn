<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import Button from 'primevue/button';
import type { components } from '../../../api/generated/schema';
import ActionFeedback from '../../../shared/ui/ActionFeedback.vue';
import { cancelRecommendationPause } from '../api/cancelRecommendationPause';
import { reverseRecommendationRejection } from '../api/reverseRecommendationRejection';
import { useRecommendationCommands } from '../composables/useRecommendationCommands';
import type { SuppressionPage } from '../models/prospecting';

const props = defineProps<{
  identity: string;
  page: SuppressionPage | undefined;
  pending: boolean;
  failed: boolean;
  fetching: boolean;
  search: string;
  offset: number;
  pageSize: number;
}>();
const emit = defineEmits<{
  search: [string];
  next: [];
  previous: [];
  refresh: [];
}>();
const commands = useRecommendationCommands(computed(() => props.identity));
const notice = ref('');
const heading = ref<HTMLHeadingElement | null>(null);
const lastBlock = ref<components['schemas']['SuppressionBlockResponse'] | null>(null);

watch(
  () => props.identity,
  () => {
    notice.value = '';
    lastBlock.value = null;
  },
  { flush: 'sync' },
);

function date(value: string | null): string {
  return value
    ? new Date(value).toLocaleString(undefined, { timeZone: 'UTC', timeZoneName: 'short' })
    : 'Indefinite';
}
function showResult(block: components['schemas']['SuppressionBlockResponse']) {
  notice.value =
    block.kind === 'pause'
      ? 'Mute removed.'
      : 'Rejection reversed. Independent blocks remain unchanged.';
}
async function clear(block: components['schemas']['SuppressionBlockResponse'], event: MouseEvent) {
  if (commands.pending.value) return;
  const trigger = event.currentTarget;
  const hadFocus = document.activeElement === trigger;
  const identity = props.identity;
  lastBlock.value = block;
  notice.value = '';
  const request = { expected_version: block.version, request_key: crypto.randomUUID() };
  const result = await commands.execute(() =>
    block.kind === 'pause'
      ? cancelRecommendationPause(block.id, request)
      : reverseRecommendationRejection(block.id, request),
  );
  if (!result || props.identity !== identity) return;
  showResult(block);
  await nextTick();
  if (
    props.identity === identity &&
    hadFocus &&
    trigger instanceof HTMLElement &&
    !trigger.isConnected &&
    document.activeElement === document.body
  )
    heading.value?.focus();
}
async function refreshCurrent(): Promise<void> {
  await commands.refresh();
  emit('refresh');
}
async function retry(): Promise<void> {
  const identity = props.identity;
  const block = lastBlock.value;
  const result = await commands.retry();
  if (result && block && props.identity === identity) showResult(block);
}
</script>

<template>
  <section class="suppression-manager" aria-labelledby="suppression-heading">
    <div class="manager-heading">
      <div>
        <h2 id="suppression-heading" ref="heading" tabindex="-1">Manage suppressions</h2>
        <p>
          These decisions apply to this Business and Company. Clearing one does not clear others.
        </p>
      </div>
      <label class="search-field">
        <span>Search companies</span>
        <input
          type="search"
          aria-label="Search suppressed companies by name or domain"
          :value="search"
          @input="emit('search', ($event.target as HTMLInputElement).value)"
        />
      </label>
    </div>
    <ActionFeedback :success="notice" :error="commands.error.value" />
    <div v-if="commands.canRetry.value" class="recovery">
      <Button
        label="Retry the same request"
        severity="secondary"
        :disabled="commands.pending.value"
        @click="retry"
      />
      <span>Retrying checks the same update safely without repeating it.</span>
    </div>
    <Button
      v-if="commands.needsRefresh.value"
      label="Refresh suppressions"
      severity="secondary"
      :disabled="commands.pending.value"
      @click="refreshCurrent"
    />
    <p v-if="pending && !page">Loading suppression decisions…</p>
    <div v-else-if="failed && !page" class="empty-error">
      <p>Suppression decisions could not be loaded.</p>
      <Button label="Retry suppressions" severity="secondary" @click="refreshCurrent" />
    </div>
    <p v-else-if="page && !page.items.length">No matching active suppression decisions.</p>
    <ul v-else-if="page" class="suppression-list" :aria-busy="fetching">
      <li v-for="item in page.items" :key="item.company_id">
        <div class="company">
          <strong>{{ item.company.name }}</strong>
          <span>{{ item.company.domain }}</span>
        </div>
        <ul class="block-list">
          <li v-for="block in item.active_blocks" :key="block.id">
            <div>
              <strong>{{ block.kind.replaceAll('_', ' ') }}</strong>
              <span v-if="block.reason"> · {{ block.reason }}</span>
              <span v-if="block.kind === 'pause'"> · until {{ date(block.expires_at) }}</span>
              <span v-else-if="block.kind === 'rejection'"> · persistent until reversed</span>
              <span class="version"> · version {{ block.version }}</span>
            </div>
            <Button
              v-if="block.kind === 'pause' || block.kind === 'rejection'"
              :label="
                block.kind === 'pause'
                  ? commands.pending.value && lastBlock?.id === block.id
                    ? 'Removing mute…'
                    : 'Remove mute'
                  : 'Reverse rejection'
              "
              :loading="commands.pending.value && lastBlock?.id === block.id"
              severity="secondary"
              :disabled="
                commands.pending.value || commands.canRetry.value || commands.needsRefresh.value
              "
              @click="clear(block, $event)"
            />
            <span v-else class="automatic">Automatic cooldown</span>
          </li>
        </ul>
      </li>
    </ul>
    <nav v-if="page" class="pagination" aria-label="Suppression pages">
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
.suppression-manager {
  display: grid;
  gap: var(--space-4);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-4);
}
.manager-heading {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  align-items: end;
  flex-wrap: wrap;
}
h2 {
  margin: 0 0 var(--space-1);
  font-size: 1.1rem;
}
p {
  margin: 0;
  color: var(--color-text-muted);
}
.search-field {
  display: grid;
  gap: var(--space-1);
  min-width: min(100%, 18rem);
}
.search-field input {
  min-height: 42px;
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
}
.suppression-list,
.block-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.suppression-list > li {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-top: 1px solid var(--color-border);
}
.company {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.company span,
.version,
.automatic,
.recovery span {
  color: var(--color-text-muted);
}
.block-list {
  display: grid;
  gap: var(--space-2);
}
.block-list li {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  align-items: center;
  flex-wrap: wrap;
  padding-left: var(--space-3);
}
.pagination,
.recovery {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
</style>
