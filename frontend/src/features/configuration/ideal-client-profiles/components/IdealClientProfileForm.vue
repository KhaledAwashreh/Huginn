<script setup lang="ts">
import { computed, ref, toRaw } from 'vue';
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import { ApiError } from '../../../../api/apiError';
import type { components } from '../../../../api/generated/schema';
import { useDirtyDraft } from '../../../../shared/forms/useDirtyDraft';
import type { IdealClientProfileDraft } from '../forms/idealClientProfileDraft';
import { serializeIdealClientProfilePatch } from '../forms/serializeIdealClientProfilePatch';
import IndustryRows from './IndustryRows.vue';
import CompanySizeRows from './CompanySizeRows.vue';
import GeographyRows from './GeographyRows.vue';
import ExclusionRows from './ExclusionRows.vue';
import { useConfigurationOptions } from '../composables/useConfigurationOptions';

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
const state = useDirtyDraft(props.initial);
const baseline = ref(structuredClone(toRaw(props.initial)));
const draft = state.draft;
const busy = ref(false);
const formError = ref('');
const validation = ref<ApiError | null>(null);
const refreshed = ref(false);
const uncertain = ref(false);
const configurationOptions = useConfigurationOptions();
const optionState = computed(() =>
  configurationOptions.isPending.value
    ? 'loading'
    : configurationOptions.isError.value
      ? 'error'
      : 'ready',
);
const industries = computed(() => configurationOptions.data.value?.industries ?? []);
const countries = computed(() => configurationOptions.data.value?.countries ?? []);
const companySizes = computed(() => configurationOptions.data.value?.company_sizes ?? []);
const canSubmit = computed(() => state.dirty.value && draft.value.name.trim() !== '');
onBeforeRouteLeave(() => (busy.value ? false : state.canLeave()));
onBeforeRouteUpdate(() => (busy.value ? false : state.canLeave()));
function normalizedPath(path: (string | number)[]): string {
  const result: (string | number)[] = [];
  for (const part of path) {
    const previous = result.at(-1);
    if (previous === part && part === 'geography') continue;
    if (
      ['company', 'industry', 'country', 'region'].includes(String(part)) &&
      typeof previous === 'number'
    )
      continue;
    if (['country', 'region'].includes(String(part)) && previous === 'geography') continue;
    result.push(part);
  }
  return result.join('.');
}
function fieldError(path: (string | number)[]): string | undefined {
  const expected = path.join('.');
  return validation.value?.fields.find((item) => normalizedPath(item.path) === expected)?.message;
}
function rowErrors(
  section: 'industries' | 'company_sizes' | 'geographies' | 'exclusions',
): string[] {
  const rows = draft.value[section];
  return rows.map((_, index) => {
    const prefix = `${section}.${index}.`;
    return (
      validation.value?.fields.find((item) => normalizedPath(item.path).startsWith(prefix))
        ?.message ?? ''
    );
  });
}
function fromResponse(
  response: components['schemas']['IdealClientProfileResponse'],
): IdealClientProfileDraft {
  return {
    name: response.name,
    industries: response.industries.map(({ name }) => ({ name })),
    company_sizes: response.company_sizes.map(({ band }) => ({ band })),
    geographies: response.geographies.map(({ kind, value }) => ({ kind, value })),
    exclusions: response.exclusions.map((item) =>
      item.kind === 'company'
        ? { kind: item.kind, company_id: item.company_id }
        : item.kind === 'industry'
          ? { kind: item.kind, name: item.name }
          : {
              kind: item.kind,
              geography: { kind: item.geography.kind, value: item.geography.value },
            },
    ),
  };
}
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
    <div class="field">
      <label for="icp-name">Name <span>(required)</span></label
      ><InputText
        id="icp-name"
        v-model="draft.name"
        :disabled="busy"
        required
        autocomplete="off"
        aria-describedby="icp-name-error"
        :aria-invalid="fieldError(['name']) ? 'true' : undefined"
      /><FieldFeedback :message="fieldError(['name']) ?? ''" />
    </div>
    <IndustryRows
      v-model="draft.industries"
      :disabled="busy"
      :errors="rowErrors('industries')"
      :options="industries"
      :state="optionState"
    />
    <CompanySizeRows
      v-model="draft.company_sizes"
      :disabled="busy"
      :errors="rowErrors('company_sizes')"
      :options="companySizes"
      :state="optionState"
    />
    <GeographyRows
      v-model="draft.geographies"
      :disabled="busy"
      :errors="rowErrors('geographies')"
      :options="countries"
      :state="optionState"
    />
    <ExclusionRows
      v-model="draft.exclusions"
      :disabled="busy"
      :errors="rowErrors('exclusions')"
      :industries="industries"
      :countries="countries"
      :state="optionState"
    />
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
