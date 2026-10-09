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
import { mergeCollectedExclusions } from '../forms/collectedOptionSelection';
import CompanyExclusionSelect from './CompanyExclusionSelect.vue';
type Exclusion =
  | components['schemas']['CompanyExclusion']
  | components['schemas']['IndustryExclusion']
  | components['schemas']['GeographyExclusion'];
const props = withDefaults(
  defineProps<{
    errors?: string[];
    disabled?: boolean;
    industries?: ConfigurationOption[];
    countries?: ConfigurationOption[];
    state?: 'loading' | 'error' | 'ready';
  }>(),
  {
    errors: () => [],
    disabled: false,
    industries: () => [],
    countries: () => [],
    state: 'loading',
  },
);
const rows = defineModel<Exclusion[]>({ required: true });
const industryValues = computed(() =>
  rows.value.filter((row) => row.kind === 'industry').map((row) => row.name),
);
const countryValues = computed(() =>
  rows.value.flatMap((row) =>
    row.kind === 'geography' && row.geography.kind === 'country' ? [row.geography.value] : [],
  ),
);
const companyRows = computed(() =>
  rows.value.flatMap((row, index) => (row.kind === 'company' ? [{ row, index }] : [])),
);
const regionRows = computed(() =>
  rows.value.flatMap((row, index) =>
    row.kind === 'geography' && row.geography.kind === 'region' ? [{ row, index }] : [],
  ),
);
const industryErrors = computed(() =>
  rows.value.flatMap((row, index) =>
    row.kind === 'industry' && props.errors?.[index] ? [props.errors[index]] : [],
  ),
);
const countryErrors = computed(() =>
  rows.value.flatMap((row, index) =>
    row.kind === 'geography' && row.geography.kind === 'country' && props.errors?.[index]
      ? [props.errors[index]]
      : [],
  ),
);
function makeOptions(
  options: ConfigurationOption[] | undefined,
  values: string[],
  excludeUnspecified = false,
) {
  const collected = (options ?? []).filter(
    (item) => item.value.trim() && (!excludeUnspecified || item.value !== 'Unspecified'),
  );
  return [
    ...collected,
    ...values
      .filter((value) => !collected.some((item) => item.value === value))
      .filter((value, index, all) => all.indexOf(value) === index)
      .map((value) => ({ value, company_count: 0, legacy: true })),
  ];
}
const industryOptions = computed(() => makeOptions(props.industries, industryValues.value, true));
const countryOptions = computed(() => makeOptions(props.countries, countryValues.value));
function label(option: ConfigurationOption & { legacy?: boolean }): string {
  const value = option.value || 'Saved blank value';
  return `${value}${option.legacy ? (props.state === 'ready' ? ' · saved value not in collected options' : ' · saved selection') : ` · ${option.company_count} companies collected`}`;
}
function updateIndustries(selected: string[]): void {
  rows.value = mergeCollectedExclusions(
    rows.value,
    selected,
    (row) => (row.kind === 'industry' ? row.name : undefined),
    (name) => ({ kind: 'industry', name }),
  );
}
function updateCountries(selected: string[]): void {
  rows.value = mergeCollectedExclusions(
    rows.value,
    selected,
    (row) =>
      row.kind === 'geography' && row.geography.kind === 'country'
        ? row.geography.value
        : undefined,
    (value) => ({ kind: 'geography', geography: { kind: 'country', value } }),
  );
}
function addCompany(): void {
  rows.value = [...rows.value, { kind: 'company', company_id: '' }];
}
function removeCompany(index: number): void {
  rows.value = rows.value.filter((_, rowIndex) => rowIndex !== index);
}
function removeRegion(index: number): void {
  rows.value = rows.value.filter((_, rowIndex) => rowIndex !== index);
}
function setCompany(index: number, id: string): void {
  const row = rows.value[index];
  if (row?.kind === 'company') rows.value[index] = { kind: 'company', company_id: id };
}
</script>
<template>
  <fieldset class="rows">
    <legend>Exclusions</legend>
    <section class="group" aria-labelledby="excluded-industries-label">
      <h3 id="excluded-industries-label">Industries</h3>
      <LoadingState v-if="state === 'loading'" message="Loading collected industries…" />
      <ErrorState
        v-else-if="state === 'error'"
        message="Collected industries could not be loaded. Saved exclusions remain available."
      />
      <EmptyState
        v-else-if="state === 'ready' && industryOptions.length === 0"
        message="No industries have been collected yet."
      />
      <label id="icp-excluded-industries-label" for="icp-excluded-industries"
        >Collected industries to exclude</label
      >
      <MultiSelect
        v-if="state === 'ready' || industryValues.length > 0"
        input-id="icp-excluded-industries"
        aria-labelledby="icp-excluded-industries-label"
        :model-value="industryValues"
        :options="industryOptions"
        :option-label="label"
        option-value="value"
        display="chip"
        :show-toggle-all="false"
        filter
        filter-placeholder="Search collected industries"
        empty-filter-message="No collected industry matches this search."
        placeholder="Select excluded industries"
        :disabled="disabled || (state !== 'ready' && industryValues.length === 0)"
        :invalid="industryErrors.length > 0"
        :aria-describedby="industryErrors.length ? 'excluded-industry-errors' : undefined"
        :pt="{ pcFilter: { root: { 'aria-label': 'Search collected industries to exclude' } } }"
        @update:model-value="updateIndustries"
      >
        <template #chip="{ value, removeCallback }">
          <Chip
            :label="value || 'Saved blank value'"
            :removable="!disabled"
            @remove="removeCallback($event, value)"
          />
        </template>
      </MultiSelect>
      <div v-if="industryErrors.length" id="excluded-industry-errors">
        <FieldFeedback v-for="(message, index) in industryErrors" :key="index" :message="message" />
      </div>
    </section>
    <section class="group" aria-labelledby="excluded-countries-label">
      <h3 id="excluded-countries-label">Countries</h3>
      <label id="icp-excluded-countries-label" for="icp-excluded-countries"
        >Collected countries to exclude</label
      >
      <MultiSelect
        input-id="icp-excluded-countries"
        aria-labelledby="icp-excluded-countries-label"
        :model-value="countryValues"
        :options="countryOptions"
        :option-label="label"
        option-value="value"
        display="chip"
        :show-toggle-all="false"
        filter
        filter-placeholder="Search collected countries"
        empty-filter-message="No collected country matches this search."
        placeholder="Select excluded countries"
        :disabled="disabled || (state !== 'ready' && countryValues.length === 0)"
        :invalid="countryErrors.length > 0"
        :aria-describedby="countryErrors.length ? 'excluded-country-errors' : undefined"
        :pt="{ pcFilter: { root: { 'aria-label': 'Search collected countries to exclude' } } }"
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
      <div v-if="countryErrors.length" id="excluded-country-errors">
        <FieldFeedback v-for="(message, index) in countryErrors" :key="index" :message="message" />
      </div>
      <LoadingState v-if="state === 'loading'" message="Loading collected countries…" />
      <ErrorState
        v-else-if="state === 'error'"
        message="Collected countries could not be loaded. Saved exclusions remain available."
      />
      <EmptyState
        v-else-if="state === 'ready' && countryOptions.length === 0"
        message="No countries have been collected yet."
      />
    </section>
    <section class="group" aria-labelledby="excluded-companies-label">
      <h3 id="excluded-companies-label">Companies</h3>
      <div v-for="({ row, index }, companyIndex) in companyRows" :key="index" class="company-row">
        <CompanyExclusionSelect
          :id="row.company_id"
          :input-key="String(index)"
          :error-id="errors?.[index] ? `exclusion-feedback-${index}` : undefined"
          :disabled="disabled"
          :invalid="Boolean(errors?.[index])"
          @update:id="setCompany(index, $event)"
        />
        <FieldFeedback :id="`exclusion-feedback-${index}`" :message="errors?.[index] ?? ''" />
        <Button
          type="button"
          severity="secondary"
          label="Remove"
          :disabled="disabled"
          :aria-label="`Remove company exclusion ${companyIndex + 1}`"
          @click="removeCompany(index)"
        />
      </div>
      <EmptyState v-if="companyRows.length === 0" message="No company exclusions selected." />
      <Button
        type="button"
        severity="secondary"
        label="Add company exclusion"
        :disabled="disabled"
        @click="addCompany"
      />
    </section>
    <section v-if="regionRows.length" class="group" aria-labelledby="excluded-regions-label">
      <h3 id="excluded-regions-label">Saved region exclusions</h3>
      <div v-for="({ row, index }, regionIndex) in regionRows" :key="index" class="region-row">
        <span
          >Region {{ regionIndex + 1 }}:
          {{ row.geography.value || 'Saved blank region value' }}</span
        >
        <FieldFeedback :id="`exclusion-feedback-${index}`" :message="errors?.[index] ?? ''" />
        <Button
          type="button"
          severity="secondary"
          label="Remove"
          :disabled="disabled"
          :aria-label="`Remove region exclusion ${regionIndex + 1}`"
          @click="removeRegion(index)"
        />
      </div>
    </section>
    <p class="notice">
      Industry and country exclusions use collected options. Company search covers the authenticated
      public Gold directory; saved unavailable companies remain selected until removed.
    </p>
    <p class="notice">
      Any matching company, industry, or country exclusion excludes that company.
    </p>
    <p class="notice">
      Company counts describe collected coverage; they do not predict combined ICP matches.
    </p>
    <p class="notice">
      If any region entry is present here, the current matcher skips the whole strategy as
      unsupported.
    </p>
  </fieldset>
</template>
<style scoped>
.rows {
  display: grid;
  gap: var(--space-4);
  border: 0;
  padding: 0;
  margin: 0;
}
.group {
  display: grid;
  gap: var(--space-2);
}
h3 {
  margin: 0;
  font-size: 1rem;
}
.company-row {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border);
}
.notice {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
</style>
