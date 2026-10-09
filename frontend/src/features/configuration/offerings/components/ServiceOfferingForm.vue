<script setup lang="ts">
import { computed, ref, toRaw } from 'vue';
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Textarea from 'primevue/textarea';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import { ApiError } from '../../../../api/apiError';
import type { components } from '../../../../api/generated/schema';
import { useDirtyDraft } from '../../../../shared/forms/useDirtyDraft';
import type { ServiceOfferingDraft } from '../forms/serviceOfferingDraft';
import { serializeServiceOfferingPatch } from '../forms/serializeServiceOfferingPatch';

const props = defineProps<{
  initial: ServiceOfferingDraft;
  existing: boolean;
  save: (
    draft: ServiceOfferingDraft,
    patch: ReturnType<typeof serializeServiceOfferingPatch>,
  ) => Promise<components['schemas']['ServiceOfferingResponse']>;
  refreshSaved: () => Promise<components['schemas']['ServiceOfferingResponse'] | null>;
  afterSave: (saved: components['schemas']['ServiceOfferingResponse']) => void | Promise<void>;
}>();
const state = useDirtyDraft(props.initial);
const baseline = ref(structuredClone(toRaw(props.initial)));
const draft = state.draft;
const busy = ref(false);
const formError = ref('');
const validation = ref<ApiError | null>(null);
const refreshed = ref(false);
const uncertain = ref(false);
const canSubmit = computed(
  () =>
    state.dirty.value && draft.value.name.trim() !== '' && draft.value.description.trim() !== '',
);
onBeforeRouteLeave(() => (busy.value ? false : state.canLeave()));
onBeforeRouteUpdate(() => (busy.value ? false : state.canLeave()));
function fieldError(field: 'name' | 'description'): string | undefined {
  return validation.value?.fields.find((item) => item.path.join('.') === field)?.message;
}
function fromResponse(
  response: components['schemas']['ServiceOfferingResponse'],
): ServiceOfferingDraft {
  return { name: response.name, description: response.description };
}
async function submit(): Promise<void> {
  if (busy.value || uncertain.value || !canSubmit.value) return;
  formError.value = '';
  validation.value = null;
  refreshed.value = false;
  busy.value = true;
  const patch = props.existing ? serializeServiceOfferingPatch(baseline.value, draft.value) : null;
  try {
    const saved = await props.save(draft.value, patch);
    const next = fromResponse(saved);
    baseline.value = structuredClone(next);
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
          ? 'This change conflicts with a strategy reference or saved record. Review the related strategy and try again.'
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
      uncertain.value = false;
      formError.value =
        'Saved data list was refreshed. Check the list to confirm whether this draft was created; it remains unchanged.';
      return;
    }
    const latest = fromResponse(response);
    baseline.value = structuredClone(latest);
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
    <p v-if="uncertain" class="refresh-row">
      <Button
        type="button"
        label="Refresh saved data"
        severity="secondary"
        @click="clickRefreshSaved"
      />
    </p>
    <p v-if="refreshed" role="status">
      Saved data was refreshed. Your draft is unchanged; review it before saving again.
    </p>
    <div class="field">
      <label for="offering-name">Name <span>(required)</span></label
      ><InputText
        id="offering-name"
        v-model="draft.name"
        :disabled="busy"
        required
        autocomplete="off"
        aria-describedby="offering-name-error"
        :aria-invalid="fieldError('name') ? 'true' : undefined"
      /><FieldFeedback id="offering-name-error" :message="fieldError('name') ?? ''" />
    </div>
    <div class="field">
      <label for="offering-description">Description <span>(required)</span></label
      ><Textarea
        id="offering-description"
        v-model="draft.description"
        :disabled="busy"
        required
        rows="5"
        aria-describedby="offering-description-error"
        :aria-invalid="fieldError('description') ? 'true' : undefined"
      /><FieldFeedback id="offering-description-error" :message="fieldError('description') ?? ''" />
    </div>
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
  max-width: 720px;
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
