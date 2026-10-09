<script setup lang="ts">
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import type { PreviousProjectDraft } from '../forms/professionalProfileDraft';
const props = defineProps<{
  modelValue: PreviousProjectDraft[];
  disabled?: boolean;
  errors?: Record<string, string>;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: PreviousProjectDraft[]] }>();
function update(index: number, key: keyof PreviousProjectDraft, value: string): void {
  emit(
    'update:modelValue',
    props.modelValue.map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: value } : row)),
  );
}
function remove(index: number): void {
  emit(
    'update:modelValue',
    props.modelValue.filter((_, i) => i !== index),
  );
}
</script>
<template>
  <fieldset class="rows" :disabled="disabled">
    <legend>Previous projects</legend>
    <section
      v-for="(row, index) in modelValue"
      :key="index"
      class="row"
      :aria-labelledby="`project-heading-${index}`"
    >
      <h3 :id="`project-heading-${index}`">Project {{ index + 1 }}</h3>
      <label :for="`project-name-${index}`">Name</label
      ><InputText
        :id="`project-name-${index}`"
        :model-value="row.name"
        :aria-invalid="Boolean(errors?.[`previous_projects.${index}.name`])"
        :aria-describedby="`project-name-error-${index}`"
        @update:model-value="update(index, 'name', String($event))"
      />
      <small
        v-if="errors?.[`previous_projects.${index}.name`]"
        :id="`project-name-error-${index}`"
        role="alert"
        >{{ errors[`previous_projects.${index}.name`] }}</small
      >
      <label :for="`project-description-${index}`">Description</label
      ><InputText
        :id="`project-description-${index}`"
        :model-value="row.description"
        :aria-invalid="Boolean(errors?.[`previous_projects.${index}.description`])"
        :aria-describedby="`project-description-error-${index}`"
        @update:model-value="update(index, 'description', String($event))"
      />
      <small
        v-if="errors?.[`previous_projects.${index}.description`]"
        :id="`project-description-error-${index}`"
        role="alert"
        >{{ errors[`previous_projects.${index}.description`] }}</small
      >
      <small v-if="errors?.[`previous_projects.${index}`]" role="alert">{{
        errors[`previous_projects.${index}`]
      }}</small>
      <Button type="button" label="Remove project" severity="secondary" @click="remove(index)" />
    </section>
    <Button
      type="button"
      label="Add project"
      severity="secondary"
      @click="emit('update:modelValue', [...modelValue, { name: '', description: '' }])"
    />
  </fieldset>
</template>
<style scoped>
.rows,
.row {
  display: grid;
  gap: var(--space-2);
}
.row {
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
}
h3 {
  margin: 0;
  font-size: 1rem;
}
legend {
  font-weight: 700;
}
</style>
