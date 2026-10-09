<script setup lang="ts">
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import type { SkillDraft } from '../forms/professionalProfileDraft';
const props = defineProps<{
  modelValue: SkillDraft[];
  disabled?: boolean;
  errors?: Record<string, string>;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: SkillDraft[]] }>();
function update(index: number, name: string): void {
  emit(
    'update:modelValue',
    props.modelValue.map((row, rowIndex) => (rowIndex === index ? { name } : row)),
  );
}
function remove(index: number): void {
  emit(
    'update:modelValue',
    props.modelValue.filter((_, rowIndex) => rowIndex !== index),
  );
}
</script>
<template>
  <fieldset class="rows" :disabled="disabled">
    <legend>Skills</legend>
    <div v-for="(row, index) in modelValue" :key="index" class="row">
      <label :for="`skill-${index}`">Skill {{ index + 1 }}</label>
      <InputText
        :id="`skill-${index}`"
        :model-value="row.name"
        :aria-invalid="Boolean(errors?.[`skills.${index}.name`])"
        :aria-describedby="`skill-error-${index}`"
        @update:model-value="update(index, String($event))"
      />
      <small v-if="errors?.[`skills.${index}.name`]" :id="`skill-error-${index}`" role="alert">{{
        errors[`skills.${index}.name`]
      }}</small>
      <Button type="button" label="Remove skill" severity="secondary" @click="remove(index)" />
    </div>
    <Button
      type="button"
      label="Add skill"
      severity="secondary"
      @click="emit('update:modelValue', [...modelValue, { name: '' }])"
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
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}
.row label,
.row small {
  grid-column: 1/-1;
}
legend {
  font-weight: 700;
}
</style>
