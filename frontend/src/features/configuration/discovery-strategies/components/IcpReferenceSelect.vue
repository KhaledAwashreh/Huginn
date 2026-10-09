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
    <label id="icps-reference-label" for="icps-reference">ICP</label>
    <Select
      input-id="icps-reference"
      aria-labelledby="icps-reference-label"
      :model-value="modelValue"
      :disabled="disabled"
      :options="items"
      option-label="name"
      option-value="id"
      filter
      :placeholder="unavailable ? 'Selected icp is unavailable' : 'Choose icp'"
      :aria-describedby="'icps-reference-feedback'"
      :aria-invalid="Boolean(feedback || unavailable)"
      @update:model-value="$emit('update:modelValue', $event)"
    />
    <FieldFeedback
      id="icps-reference-feedback"
      :message="
        feedback ||
        error ||
        (unavailable
          ? 'The selected icp was removed or is unavailable. Choose an available reference.'
          : '')
      "
    />
    <Button
      v-if="hasMore"
      type="button"
      label="Load more icps"
      severity="secondary"
      :loading="loading"
      :disabled="loading || disabled"
      @click="$emit('more')"
    />
    <RouterLink to="/icps/new">Create icp</RouterLink>
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
