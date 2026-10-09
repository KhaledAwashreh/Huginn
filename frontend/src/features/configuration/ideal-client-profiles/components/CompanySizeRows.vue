<script setup lang="ts">
import { computed } from 'vue';
import SelectButton from 'primevue/selectbutton';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import type { ConfigurationOption } from '../api/getConfigurationOptions';
import type { components } from '../../../../api/generated/schema';
import { mergeCollectedValues } from '../forms/collectedOptionSelection';

const props = withDefaults(
  defineProps<{
    errors?: string[];
    disabled?: boolean;
    options?: ConfigurationOption[];
    state?: 'loading' | 'error' | 'ready';
  }>(),
  { errors: () => [], disabled: false, options: () => [], state: 'loading' },
);
const rows = defineModel<components['schemas']['CompanySize'][]>({ required: true });
const bands = ['0-10', '11-100', '101-1000', '1001+'] as const;
const values = computed(() => rows.value.map((row) => row.band));
const options = computed(() => {
  const fixed = bands.map((value) => ({
    value,
    label: value,
  }));
  return [
    ...fixed,
    ...values.value
      .filter((value) => !bands.includes(value as (typeof bands)[number]))
      .filter((value, index, all) => all.indexOf(value) === index)
      .map((value) => ({
        value,
        label: `${value}${props.state === 'ready' ? ' · saved value not in collected options' : ' · saved selection'}`,
      })),
  ];
});
function update(selected: string[]): void {
  rows.value = mergeCollectedValues(
    rows.value,
    selected,
    (row) => row.band,
    (band) => ({ band: band as (typeof bands)[number] }),
  );
}
</script>
<template>
  <fieldset class="rows">
    <legend>Company sizes</legend>
    <label id="icp-company-sizes-label" for="icp-company-sizes">Company size bands</label>
    <LoadingState v-if="state === 'loading'" message="Loading collected company size coverage…" />
    <ErrorState
      v-else-if="state === 'error'"
      message="Collected size coverage could not be loaded. Saved selections remain available."
    />
    <SelectButton
      input-id="icp-company-sizes"
      aria-labelledby="icp-company-sizes-label"
      :model-value="[...new Set(values)]"
      :options="options"
      option-label="label"
      option-value="value"
      multiple
      :disabled="disabled"
      :aria-invalid="errors?.some(Boolean) ? 'true' : undefined"
      :aria-describedby="errors?.some(Boolean) ? 'size-errors' : undefined"
      @update:model-value="update"
    />
    <p v-if="values.length === 0" class="note">
      No size bands selected. You can still save this ICP; matching will be incomplete until
      criteria are selected.
    </p>
    <div v-if="errors?.some(Boolean)" id="size-errors">
      <FieldFeedback v-for="(message, index) in errors" :key="index" :message="message" />
    </div>
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
.rows :deep(.p-selectbutton) {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
.rows :deep(.p-togglebutton:not(:disabled)) {
  color: var(--color-text);
}
.note {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
</style>
