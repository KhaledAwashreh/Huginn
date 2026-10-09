<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import Select from 'primevue/select';
import type { MatchmakingTriggerDraft } from '../forms/matchmakingTriggerDraft';
const props = defineProps<{ modelValue: MatchmakingTriggerDraft }>();
const emit = defineEmits<{ 'update:modelValue': [value: MatchmakingTriggerDraft] }>();
const preset = ref(props.modelValue.windowPreset);
const presets = [
  { label: 'Last 7 days', value: '7' },
  { label: 'Last 30 days', value: '30' },
  { label: 'Last 90 days', value: '90' },
  { label: 'Custom', value: 'custom' },
];
const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time';
function validUtc(value: string): string {
  if (!value) return 'Choose a date and time';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Enter a valid date and time' : date.toISOString();
}
const utcCutoff = computed(() => validUtc(props.modelValue.cutoffLocal));
const utcAsOf = computed(() => validUtc(props.modelValue.asOfLocal));
watch(preset, (value) => {
  if (value === 'custom') {
    emit('update:modelValue', { ...props.modelValue, windowPreset: 'custom' });
    return;
  }
  const end = new Date();
  const start = new Date(end.getTime() - Number(value) * 86_400_000);
  const local = (date: Date) => {
    const adjusted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return adjusted.toISOString().slice(0, 16);
  };
  emit('update:modelValue', {
    ...props.modelValue,
    windowPreset: value as MatchmakingTriggerDraft['windowPreset'],
    cutoffLocal: local(start),
    asOfLocal: local(end),
  });
});
function update(field: 'cutoffLocal' | 'asOfLocal', value: string) {
  preset.value = 'custom';
  emit('update:modelValue', { ...props.modelValue, windowPreset: 'custom', [field]: value });
}
</script>

<template>
  <fieldset class="window-fields">
    <legend>Signal window</legend>
    <label id="window-preset-label" for="window-preset">Window preset</label>
    <Select
      v-model="preset"
      input-id="window-preset"
      aria-labelledby="window-preset-label"
      :options="presets"
      option-label="label"
      option-value="value"
    />
    <div class="dates">
      <label
        >Start in {{ localZone
        }}<input
          type="datetime-local"
          :value="modelValue.cutoffLocal"
          @input="update('cutoffLocal', ($event.target as HTMLInputElement).value)"
      /></label>
      <label
        >End in {{ localZone
        }}<input
          type="datetime-local"
          :value="modelValue.asOfLocal"
          @input="update('asOfLocal', ($event.target as HTMLInputElement).value)"
      /></label>
    </div>
    <p class="utc-preview">UTC preview: {{ utcCutoff }} through {{ utcAsOf }}</p>
  </fieldset>
</template>

<style scoped>
.window-fields {
  display: grid;
  gap: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  padding: var(--space-4);
}
.dates {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: var(--space-3);
}
.dates label {
  display: grid;
  gap: var(--space-2);
}
.dates input {
  min-height: 44px;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
}
.utc-preview {
  overflow-wrap: anywhere;
  color: var(--color-text-muted);
}
</style>
