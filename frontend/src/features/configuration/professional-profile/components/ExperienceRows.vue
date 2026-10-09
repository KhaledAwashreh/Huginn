<script setup lang="ts">
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import type { ExperienceDraft } from '../forms/professionalProfileDraft';
const props = defineProps<{
  modelValue: ExperienceDraft[];
  disabled?: boolean;
  errors?: Record<string, string>;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: ExperienceDraft[]] }>();
function update(index: number, key: keyof ExperienceDraft, value: string | boolean): void {
  emit(
    'update:modelValue',
    props.modelValue.map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: value } : row)),
  );
}
function setCurrent(index: number, isCurrent: boolean): void {
  emit(
    'update:modelValue',
    props.modelValue.map((row, rowIndex) =>
      rowIndex === index
        ? { ...row, is_current: isCurrent, ...(isCurrent ? { end_month: '' } : {}) }
        : row,
    ),
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
    <legend>Experience</legend>
    <section
      v-for="(row, index) in modelValue"
      :key="index"
      class="row"
      :aria-labelledby="`experience-heading-${index}`"
    >
      <h3 :id="`experience-heading-${index}`">Experience {{ index + 1 }}</h3>
      <label :for="`experience-org-${index}`">Organization</label
      ><InputText
        :id="`experience-org-${index}`"
        :model-value="row.organization"
        :aria-invalid="Boolean(errors?.[`experience.${index}.organization`])"
        :aria-describedby="`experience-organization-error-${index}`"
        @update:model-value="update(index, 'organization', String($event))"
      />
      <small
        v-if="errors?.[`experience.${index}.organization`]"
        :id="`experience-organization-error-${index}`"
        role="alert"
        >{{ errors[`experience.${index}.organization`] }}</small
      >
      <label :for="`experience-role-${index}`">Role</label
      ><InputText
        :id="`experience-role-${index}`"
        :model-value="row.role"
        :aria-invalid="Boolean(errors?.[`experience.${index}.role`])"
        :aria-describedby="`experience-role-error-${index}`"
        @update:model-value="update(index, 'role', String($event))"
      />
      <small
        v-if="errors?.[`experience.${index}.role`]"
        :id="`experience-role-error-${index}`"
        role="alert"
        >{{ errors[`experience.${index}.role`] }}</small
      >
      <label :for="`experience-summary-${index}`">Summary (optional)</label
      ><InputText
        :id="`experience-summary-${index}`"
        :model-value="row.summary"
        :aria-invalid="Boolean(errors?.[`experience.${index}.summary`])"
        :aria-describedby="`experience-summary-error-${index}`"
        @update:model-value="update(index, 'summary', String($event))"
      />
      <small
        v-if="errors?.[`experience.${index}.summary`]"
        :id="`experience-summary-error-${index}`"
        role="alert"
        >{{ errors[`experience.${index}.summary`] }}</small
      >
      <label :for="`experience-start-${index}`">Start month (optional)</label
      ><InputText
        :id="`experience-start-${index}`"
        type="month"
        :model-value="row.start_month"
        :aria-invalid="Boolean(errors?.[`experience.${index}.start_month`])"
        :aria-describedby="`experience-start-error-${index}`"
        @update:model-value="update(index, 'start_month', String($event))"
      />
      <small
        v-if="errors?.[`experience.${index}.start_month`]"
        :id="`experience-start-error-${index}`"
        role="alert"
        >{{ errors[`experience.${index}.start_month`] }}</small
      >
      <label :for="`experience-end-${index}`">End month (optional)</label
      ><InputText
        :id="`experience-end-${index}`"
        :type="row.is_current ? 'text' : 'month'"
        :model-value="row.is_current ? 'Present' : row.end_month"
        :disabled="disabled || row.is_current"
        :aria-invalid="Boolean(errors?.[`experience.${index}.end_month`])"
        :aria-describedby="`experience-end-error-${index}`"
        @update:model-value="update(index, 'end_month', String($event))"
      />
      <small
        v-if="errors?.[`experience.${index}.end_month`]"
        :id="`experience-end-error-${index}`"
        role="alert"
        >{{ errors[`experience.${index}.end_month`] }}</small
      >
      <label
        ><input
          type="checkbox"
          :checked="row.is_current"
          :disabled="disabled || (modelValue.some((item) => item.is_current) && !row.is_current)"
          @change="setCurrent(index, ($event.target as HTMLInputElement).checked)"
        />
        Current role</label
      >
      <small v-if="errors?.[`experience.${index}`]" role="alert">{{
        errors[`experience.${index}`]
      }}</small>
      <Button type="button" label="Remove experience" severity="secondary" @click="remove(index)" />
    </section>
    <Button
      type="button"
      label="Add experience"
      severity="secondary"
      @click="
        emit('update:modelValue', [
          ...modelValue,
          {
            organization: '',
            role: '',
            summary: '',
            start_month: '',
            end_month: '',
            is_current: false,
          },
        ])
      "
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
