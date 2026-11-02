<script setup lang="ts">
import { useId } from 'vue';
import { Plus } from '@lucide/vue';
import { awaitingBackendAttrs } from '../../../shared/availability/awaitingBackend';

defineProps<{
  title: string;
  addLabel?: string | undefined;
  // The add action has no backend yet, so it stays visible but disabled.
  addAwaitsBackend?: boolean;
}>();
defineEmits<{ add: [] }>();
const headingId = useId();
</script>

<template>
  <section class="profile-section" :aria-labelledby="headingId">
    <div class="section-heading">
      <h2 :id="headingId">{{ title }}</h2>
      <button
        v-if="addLabel"
        v-bind="addAwaitsBackend ? awaitingBackendAttrs : {}"
        type="button"
        class="add-button"
        :aria-label="addLabel"
        @click="$emit('add')"
      >
        <Plus :size="18" aria-hidden="true" />
      </button>
    </div>
    <slot />
  </section>
</template>

<style scoped>
.profile-section {
  display: grid;
  gap: var(--space-2);
}
.section-heading {
  min-height: 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}
.add-button {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
}
.add-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.add-button:not(:disabled):hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}
</style>
