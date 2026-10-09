<script setup lang="ts">
import { computed } from 'vue';
import MultiSelect from 'primevue/multiselect';
import Chip from 'primevue/chip';
import Button from 'primevue/button';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import EmptyState from '../../../../shared/ui/EmptyState.vue';
import type { components } from '../../../../api/generated/schema';
import type { ConfigurationOption } from '../api/getConfigurationOptions';
import { mergeCollectedValues } from '../forms/collectedOptionSelection';
type Geography =
  components['schemas']['CountryGeography'] | components['schemas']['RegionGeography'];
const props = withDefaults(
  defineProps<{
    errors?: string[];
    disabled?: boolean;
    options?: ConfigurationOption[];
    state?: 'loading' | 'error' | 'ready';
  }>(),
  { errors: () => [], disabled: false, options: () => [], state: 'loading' },
);
const rows = defineModel<Geography[]>({ required: true });
const countries = computed(() =>
  rows.value.filter((row) => row.kind === 'country').map((row) => row.value),
);
const collectedCountries = computed(() =>
  (props.options ?? []).filter((item) => item.value.trim()),
);
const countryOptions = computed(() => [
  ...collectedCountries.value,
  ...countries.value
    .filter((value) => !collectedCountries.value.some((item) => item.value === value))
    .filter((value, index, all) => all.indexOf(value) === index)
    .map((value) => ({ value, company_count: 0, legacy: true })),
]);
function label(option: ConfigurationOption & { legacy?: boolean }): string {
  const value = option.value || 'Saved blank value';
  return `${value}${option.legacy ? (props.state === 'ready' ? ' · saved value not in collected options' : ' · saved selection') : ` · ${option.company_count} companies collected`}`;
}
function updateCountries(selected: string[]): void {
  const nextCountries = mergeCollectedValues(
    rows.value.filter((row) => row.kind === 'country'),
    selected,
    (row) => row.value,
    (value) => ({ kind: 'country' as const, value }),
  );
  const remainingCountries = [...nextCountries];
  const rebuilt: Geography[] = [];
  for (const row of rows.value) {
    if (row.kind === 'country') {
      const keptIndex = remainingCountries.findIndex((country) => country.value === row.value);
      if (keptIndex >= 0) {
        remainingCountries.splice(keptIndex, 1);
        rebuilt.push(row);
      }
    } else {
      rebuilt.push(row);
    }
  }
  rebuilt.push(...remainingCountries);
  rows.value = rebuilt;
}
function removeRegion(index: number): void {
  let seen = -1;
  const global = rows.value.findIndex((row) => row.kind === 'region' && ++seen === index);
  if (global >= 0) rows.value = rows.value.filter((_, rowIndex) => rowIndex !== global);
}
</script>
<template>
  <fieldset class="rows">
    <legend>Geographies</legend>
    <label id="icp-countries-label" for="icp-countries">Collected countries</label>
    <LoadingState v-if="state === 'loading'" message="Loading collected countries…" />
    <ErrorState
      v-else-if="state === 'error'"
      message="Collected countries could not be loaded. Saved selections remain available."
    />
    <EmptyState
      v-else-if="state === 'ready' && countryOptions.length === 0"
      message="No countries have been collected yet. You can still save this ICP; matching will be incomplete until criteria are selected."
    />
    <MultiSelect
      v-if="countryOptions.length > 0"
      input-id="icp-countries"
      aria-labelledby="icp-countries-label"
      :model-value="countries"
      :options="countryOptions"
      :option-label="label"
      option-value="value"
      display="chip"
      :show-toggle-all="false"
      filter
      filter-placeholder="Search collected countries"
      empty-filter-message="No collected country matches this search."
      placeholder="Select countries"
      :disabled="disabled || (state !== 'ready' && countries.length === 0)"
      :invalid="Boolean(errors?.some(Boolean))"
      :aria-describedby="errors?.some(Boolean) ? 'geography-errors' : undefined"
      :pt="{ pcFilter: { root: { 'aria-label': 'Search collected countries' } } }"
      @update:model-value="updateCountries"
    >
      <template #chip="{ value, removeCallback }">
        <Chip
          :label="value || 'Saved blank value'"
          :removable="!disabled"
          @remove="removeCallback($event, value)"
        />
      </template>
    </MultiSelect>
    <div v-if="errors?.some(Boolean)" id="geography-errors">
      <FieldFeedback
        v-for="(message, index) in errors ?? []"
        :id="`geography-feedback-${index}`"
        :key="index"
        :message="message"
      />
    </div>
    <p v-if="countries.length === 0" class="note">
      No countries selected. You can still save this ICP; matching will be incomplete until criteria
      are selected.
    </p>
    <div class="regions">
      <label
        v-for="(row, index) in rows.filter((item) => item.kind === 'region')"
        :key="index"
        :for="`region-${index}`"
      >
        Region {{ index + 1 }}
        <span class="region-row">
          <span>{{ row.value || 'Saved blank region value' }}</span>
          <Button
            type="button"
            severity="secondary"
            label="Remove"
            :disabled="disabled"
            :aria-label="`Remove region ${index + 1}`"
            @click="removeRegion(index)"
          />
        </span>
      </label>
    </div>
    <p class="notice">
      If any region entry is present here, the current matcher skips the whole strategy as
      unsupported.
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
.regions {
  display: grid;
  gap: var(--space-2);
}
.region-row {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.notice,
.note {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
</style>
