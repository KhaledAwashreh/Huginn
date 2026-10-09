<script setup lang="ts">
import { computed } from 'vue';
import MultiSelect from 'primevue/multiselect';
import Chip from 'primevue/chip';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import EmptyState from '../../../../shared/ui/EmptyState.vue';
import type { components } from '../../../../api/generated/schema';
import { mergeCollectedValues } from '../forms/collectedOptionSelection';
import type { ConfigurationOption } from '../api/getConfigurationOptions';

const props = withDefaults(
  defineProps<{
    errors?: string[];
    disabled?: boolean;
    options?: ConfigurationOption[];
    state?: 'loading' | 'error' | 'ready';
  }>(),
  { errors: () => [], disabled: false, options: () => [], state: 'loading' },
);
const rows = defineModel<components['schemas']['Industry'][]>({ required: true });
const values = computed(() => rows.value.map((row) => row.name));
const options = computed(() => {
  const current = new Set(values.value);
  const collected = (props.options ?? []).filter(
    (item) => item.value.trim() && item.value !== 'Unspecified',
  );
  return [
    ...collected,
    ...values.value
      .filter((value) => !collected.some((item) => item.value === value))
      .filter((value, index, all) => all.indexOf(value) === index)
      .map((value) => ({ value, company_count: 0, legacy: true })),
  ].filter((item) => !('legacy' in item) || current.has(item.value));
});
function label(option: ConfigurationOption & { legacy?: boolean }): string {
  const value = option.value || 'Saved blank value';
  return `${value}${option.legacy ? (props.state === 'ready' ? ' · saved value not in collected options' : ' · saved selection') : ` · ${option.company_count} companies collected`}`;
}
function update(selected: string[]): void {
  rows.value = mergeCollectedValues(
    rows.value,
    selected,
    (row) => row.name,
    (name) => ({ name }),
  );
}
</script>
<template>
  <fieldset class="rows">
    <legend>Industries</legend>
    <label id="icp-industries-label" for="icp-industries">Collected industry options</label>
    <LoadingState v-if="state === 'loading'" message="Loading collected industries…" />
    <ErrorState
      v-else-if="state === 'error'"
      message="Collected industries could not be loaded. Saved selections remain available."
    />
    <EmptyState
      v-else-if="state === 'ready' && options.length === 0"
      message="No industries have been collected yet. You can still save this ICP; matching will be incomplete until criteria are selected."
    />
    <MultiSelect
      v-if="options.length > 0"
      input-id="icp-industries"
      aria-labelledby="icp-industries-label"
      :model-value="values"
      :options="options"
      :option-label="label"
      option-value="value"
      display="chip"
      :show-toggle-all="false"
      filter
      filter-placeholder="Search collected industries"
      empty-filter-message="No collected industry matches this search."
      placeholder="Select industries"
      :disabled="disabled || (state !== 'ready' && values.length === 0)"
      :invalid="Boolean(errors?.some(Boolean))"
      :aria-describedby="errors?.some(Boolean) ? 'industry-errors' : undefined"
      :pt="{ pcFilter: { root: { 'aria-label': 'Search collected industries' } } }"
      @update:model-value="update"
    >
      <template #chip="{ value, removeCallback }">
        <Chip
          :label="value || 'Saved blank value'"
          :removable="!disabled"
          @remove="removeCallback($event, value)"
        />
      </template>
    </MultiSelect>
    <div v-if="errors?.some(Boolean)" id="industry-errors">
      <FieldFeedback v-for="(message, index) in errors" :key="index" :message="message" />
    </div>
    <p v-if="values.length === 0" class="note">
      No industries selected. You can still save this ICP; matching will be incomplete until
      criteria are selected.
    </p>
    <p class="note">
      Company counts describe collected coverage. They do not predict combined ICP matches.
    </p>
  </fieldset>
</template>
<style scoped>
.rows {
  display: grid;
  gap: var(--space-2);
  border: 0;
  padding: 0;
  margin: 0;
}
.note {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
</style>
