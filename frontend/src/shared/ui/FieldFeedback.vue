<script setup lang="ts">
defineProps<{
  message?: string;
  id?: string;
}>();
</script>

<template>
  <p v-if="message" :id="id" class="field-feedback" role="alert">{{ message }}</p>
</template>

<style scoped>
.field-feedback {
  margin: var(--space-1) 0 0;
  color: var(--color-danger-text);
  font-size: 0.875rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
</style>
