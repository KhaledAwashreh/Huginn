<script setup lang="ts">
import { computed, inject, ref } from 'vue';
import { matchedRouteKey, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import Button from 'primevue/button';
import { ApiError } from '../../../../api/apiError';
import type { components } from '../../../../api/generated/schema';
import { useDirtyDraft } from '../../../../shared/forms/useDirtyDraft';
import {
  createIdealClientProfileDraft,
  type IdealClientProfileDraft,
} from '../forms/idealClientProfileDraft';
import { serializeIdealClientProfilePatch } from '../forms/serializeIdealClientProfilePatch';
import IdealClientProfileFields from './IdealClientProfileFields.vue';
import { icpSelectionConflicts } from '../forms/icpSelectionConflicts';

const props = defineProps<{
  initial: IdealClientProfileDraft;
  existing: boolean;
  save: (
    draft: IdealClientProfileDraft,
    patch: ReturnType<typeof serializeIdealClientProfilePatch>,
  ) => Promise<components['schemas']['IdealClientProfileResponse']>;
  refreshSaved: () => Promise<components['schemas']['IdealClientProfileResponse'] | null>;
  afterSave: (saved: components['schemas']['IdealClientProfileResponse']) => void | Promise<void>;
}>();
const state = useDirtyDraft(createIdealClientProfileDraft(props.initial));
const baseline = ref(createIdealClientProfileDraft(props.initial));
const draft = state.draft;
const busy = ref(false);
const formError = ref('');
const validation = ref<ApiError | null>(null);
const refreshed = ref(false);
const uncertain = ref(false);
const conflicts = computed(() => icpSelectionConflicts(draft.value));
const canSubmit = computed(
  () => state.dirty.value && draft.value.name.trim() !== '' && conflicts.value.length === 0,
);
function canClose(): boolean | Promise<boolean> {
  return busy.value ? false : state.canLeave();
}
if (inject(matchedRouteKey, null)) {
  onBeforeRouteLeave(canClose);
  onBeforeRouteUpdate(canClose);
}
// Closing the settings modal is not a navigation, so it asks the form directly.
defineExpose({ canClose });
async function submit(): Promise<void> {
  if (busy.value || uncertain.value || !canSubmit.value) return;
  formError.value = '';
  validation.value = null;
  refreshed.value = false;
  busy.value = true;
  const patch = props.existing
    ? serializeIdealClientProfilePatch(baseline.value, draft.value)
    : null;
  try {
    const saved = await props.save(createIdealClientProfileDraft(draft.value), patch);
    const next = createIdealClientProfileDraft(saved);
    baseline.value = createIdealClientProfileDraft(next);
    state.accept(next);
    if (!props.existing) {
      busy.value = false;
      await props.afterSave(saved);
    }
  } catch (error) {
    if (error instanceof ApiError && error.status < 500) {
      validation.value = error;
      formError.value =
        error.status === 409
          ? 'This ICP conflicts with a saved reference or record. Review the related strategy and try again.'
          : error.message;
    } else {
      uncertain.value = true;
      formError.value =
        'The save outcome is uncertain. Your draft is still here. Refresh saved data before choosing whether to save again.';
    }
  } finally {
    busy.value = false;
  }
}
async function clickRefreshSaved(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  try {
    const response = await props.refreshSaved();
    if (!response) {
      refreshed.value = true;
      formError.value =
        'The saved list was refreshed, but the create result is still uncertain. Review ICP definitions before starting another create; this draft cannot be submitted again.';
      return;
    }
    const latest = createIdealClientProfileDraft(response);
    baseline.value = createIdealClientProfileDraft(latest);
    state.updateBaseline(latest);
    uncertain.value = false;
    refreshed.value = true;
    formError.value = '';
  } catch {
    formError.value =
      'Saved data could not be refreshed. Your draft is still here, and saving remains paused.';
  } finally {
    busy.value = false;
  }
}
function cancel(): void {
  state.reset();
  uncertain.value = false;
  validation.value = null;
  formError.value = '';
}
</script>
<template>
  <form class="editor" novalidate @submit.prevent="submit">
    <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
    <p v-for="conflict in conflicts" :key="conflict" class="form-error" role="alert">
      {{ conflict }}
    </p>
    <Button
      v-if="uncertain"
      type="button"
      label="Refresh saved data"
      severity="secondary"
      @click="clickRefreshSaved"
    />
    <p v-if="refreshed" role="status">
      Saved data was refreshed. Your draft is unchanged; review it before saving again.
    </p>
    <IdealClientProfileFields v-model="draft" :disabled="busy" :validation="validation" />
    <div class="actions">
      <Button
        type="submit"
        label="Save changes"
        :disabled="!canSubmit || busy || uncertain"
        :loading="busy"
      /><Button
        type="button"
        label="Cancel"
        severity="secondary"
        :disabled="!state.dirty.value || busy"
        @click="cancel"
      />
    </div>
  </form>
</template>
<style scoped>
.editor {
  display: grid;
  gap: var(--space-4);
  max-width: 820px;
}
.field {
  display: grid;
  gap: var(--space-2);
}
label {
  font-weight: 600;
}
.field label span {
  font-weight: 400;
  color: var(--color-text-muted);
}
.actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.form-error {
  padding: var(--space-3);
  background: var(--color-danger-surface);
  color: var(--color-danger-text);
  overflow-wrap: anywhere;
}
</style>
