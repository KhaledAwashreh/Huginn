<script setup lang="ts">
import Select from 'primevue/select';
import Button from 'primevue/button';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
defineProps<{
  modelValue: string;
  disabled: boolean;
  items: { id: string; name: string }[];
  hasMore: boolean;
  loading: boolean;
  unavailable: boolean;
  error: string;
  feedback: string;
}>();
defineEmits<{ 'update:modelValue': [value: string]; more: [] }>();
</script>
<template>
  <div class="reference-select">
    <label id="offerings-reference-label" for="offerings-reference">Service offering</label>
    <Select
      input-id="offerings-reference"
      aria-labelledby="offerings-reference-label"
      :model-value="modelValue"
      :disabled="disabled"
      :options="items"
      option-label="name"
      option-value="id"
      filter
      :placeholder="
        unavailable ? 'Selected service offering is unavailable' : 'Choose service offering'
      "
      :aria-describedby="'offerings-reference-feedback'"
      :aria-invalid="Boolean(feedback || unavailable)"
      @update:model-value="$emit('update:modelValue', $event)"
    />
    <FieldFeedback
      id="offerings-reference-feedback"
      :message="
        feedback ||
        error ||
        (unavailable
          ? 'The selected service offering was removed or is unavailable. Choose an available reference.'
          : '')
      "
    />
    <Button
      v-if="hasMore"
      type="button"
      label="Load more service offerings"
      severity="secondary"
      :loading="loading"
      :disabled="loading || disabled"
      @click="$emit('more')"
    />
    <RouterLink to="/offerings/new">Create service offering</RouterLink>
  </div>
</template>
<style scoped>
.reference-select {
  display: grid;
  gap: var(--space-2);
}
a {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
}
</style>
