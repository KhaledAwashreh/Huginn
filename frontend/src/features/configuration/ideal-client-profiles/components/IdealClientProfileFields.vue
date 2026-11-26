<script setup lang="ts">
import { computed } from 'vue';
import InputText from 'primevue/inputtext';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import type { ApiError } from '../../../../api/apiError';
import type { IdealClientProfileDraft } from '../forms/idealClientProfileDraft';
import IndustryRows from './IndustryRows.vue';
import CompanySizeRows from './CompanySizeRows.vue';
import GeographyRows from './GeographyRows.vue';
import ExclusionRows from './ExclusionRows.vue';
import { useConfigurationOptions } from '../composables/useConfigurationOptions';

const props = defineProps<{ disabled?: boolean; validation?: ApiError | null }>();
const draft = defineModel<IdealClientProfileDraft>({ required: true });
const configurationOptions = useConfigurationOptions();
const optionState = computed(() =>
  configurationOptions.isPending.value
    ? 'loading'
    : configurationOptions.isError.value
      ? 'error'
      : 'ready',
);
const industries = computed(() => configurationOptions.data.value?.industries ?? []);
const countries = computed(() => configurationOptions.data.value?.countries ?? []);
const companySizes = computed(() => configurationOptions.data.value?.company_sizes ?? []);
const excludedIndustries = computed(() =>
  draft.value.exclusions.flatMap((item) => (item.kind === 'industry' ? [item.name] : [])),
);
const excludedCountries = computed(() =>
  draft.value.exclusions.flatMap((item) =>
    item.kind === 'geography' && item.geography.kind === 'country' ? [item.geography.value] : [],
  ),
);
function normalizedPath(path: (string | number)[]): string {
  const result: (string | number)[] = [];
  for (const part of path) {
    const previous = result.at(-1);
    if (previous === part && part === 'geography') continue;
    if (
      ['company', 'industry', 'country', 'region'].includes(String(part)) &&
      typeof previous === 'number'
    )
      continue;
    if (['country', 'region'].includes(String(part)) && previous === 'geography') continue;
    result.push(part);
  }
  return result.join('.');
}
function fieldError(path: (string | number)[]): string | undefined {
  const expected = path.join('.');
  return props.validation?.fields.find((item) => normalizedPath(item.path) === expected)?.message;
}
function rowErrors(
  section: 'industries' | 'company_sizes' | 'geographies' | 'exclusions',
): string[] {
  const rows = draft.value[section];
  return rows.map((_, index) => {
    const prefix = `${section}.${index}.`;
    return (
      props.validation?.fields.find((item) => normalizedPath(item.path).startsWith(prefix))
        ?.message ?? ''
    );
  });
}
</script>
<template>
  <div class="icp-fields">
    <div class="field">
      <label for="icp-name">Name <span>(required)</span></label
      ><InputText
        id="icp-name"
        v-model="draft.name"
        :disabled="disabled"
        required
        autocomplete="off"
        aria-describedby="icp-name-error"
        :aria-invalid="fieldError(['name']) ? 'true' : undefined"
      /><FieldFeedback id="icp-name-error" :message="fieldError(['name']) ?? ''" />
    </div>
    <IndustryRows
      v-model="draft.industries"
      :blocked-values="excludedIndustries"
      :disabled="disabled"
      :errors="rowErrors('industries')"
      :options="industries"
      :state="optionState"
    />
    <CompanySizeRows
      v-model="draft.company_sizes"
      :disabled="disabled"
      :errors="rowErrors('company_sizes')"
      :options="companySizes"
      :state="optionState"
    />
    <GeographyRows
      v-model="draft.geographies"
      :blocked-values="excludedCountries"
      :disabled="disabled"
      :errors="rowErrors('geographies')"
      :options="countries"
      :state="optionState"
    />
    <ExclusionRows
      v-model="draft.exclusions"
      :blocked-industries="draft.industries.map((item) => item.name)"
      :blocked-countries="
        draft.geographies.flatMap((item) => (item.kind === 'country' ? [item.value] : []))
      "
      :disabled="disabled"
      :errors="rowErrors('exclusions')"
      :industries="industries"
      :countries="countries"
      :state="optionState"
    />
  </div>
</template>
<style scoped>
.icp-fields,
.field {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}
.field {
  gap: var(--space-2);
}
label {
  font-weight: 600;
}
.field label span {
  font-weight: 400;
  color: var(--color-text-muted);
}
</style>
