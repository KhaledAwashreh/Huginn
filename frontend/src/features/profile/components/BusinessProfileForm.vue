<script setup lang="ts">
import { computed, ref, toRaw } from 'vue';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import InputText from 'primevue/inputtext';
import Textarea from 'primevue/textarea';
import { ApiError } from '../../../api/apiError';
import type { FieldError } from '../../../api/apiError';
import { useDirtyDraft } from '../../../shared/forms/useDirtyDraft';
import FieldFeedback from '../../../shared/ui/FieldFeedback.vue';
import { useBusinessProfile } from '../composables/useBusinessProfile';
import { createBusinessProfileDraft } from '../forms/businessProfileDraft';
import type { BusinessProfileDraft } from '../forms/businessProfileDraft';
import { serializeBusinessProfilePatch } from '../forms/serializeBusinessProfilePatch';
import { websiteUrl } from '../lib/profileFormatting';
import type { BusinessProfile } from '../models/businessProfile';

const props = defineProps<{
  visible: boolean;
  profile: BusinessProfile;
}>();
const emit = defineEmits<{ 'update:visible': [visible: boolean] }>();
const initialIdentity = { id: props.profile.id, ownerUserId: props.profile.owner_user_id };
const baseline = ref(props.profile);
const state = useDirtyDraft(createBusinessProfileDraft(baseline.value));
const draft = state.draft;
const { business, save } = useBusinessProfile();
const refreshing = ref(false);
const pending = computed(() => save.isPending.value || refreshing.value);
const uncertain = ref(false);
const error = ref('');
const status = ref('');
const errors = ref<Record<string, string>>({});
const capabilityText = computed({
  get: () => draft.value.capabilities.join('\n'),
  set: (value: string) => {
    draft.value.capabilities = value.split(/\r?\n/);
  },
});
const canSubmit = computed(() => state.dirty.value && !pending.value && !uncertain.value);

function canClose(): boolean | Promise<boolean> {
  return pending.value ? false : state.canLeave();
}
defineExpose({ canClose });

function applyErrors(fields: FieldError[]): void {
  for (const field of fields) {
    const path = field.path.map(String).join('.');
    if (['name', 'tagline', 'website', 'location', 'description', 'capabilities'].includes(path))
      errors.value[path] = field.message;
  }
}

async function close(): Promise<void> {
  if (pending.value) return;
  if (await state.canLeave()) emit('update:visible', false);
}

function responseHasIdentity(profile: BusinessProfile): boolean {
  return profile.id === initialIdentity.id && profile.owner_user_id === initialIdentity.ownerUserId;
}

function profileValue(
  profile: BusinessProfile,
  field: keyof BusinessProfileDraft,
): string | string[] {
  if (field === 'capabilities') return (profile.capabilities ?? []).map(({ name }) => name);
  return profile[field] ?? '';
}

function patchMatches(
  profile: BusinessProfile,
  patch: ReturnType<typeof serializeBusinessProfilePatch>,
): boolean {
  if (!patch) return true;
  for (const field of Object.keys(patch) as (keyof BusinessProfileDraft)[]) {
    if (field === 'capabilities') {
      const expected = (patch.capabilities ?? []).map(({ name }) => name);
      const actual = profileValue(profile, field) as string[];
      if (
        expected.length !== actual.length ||
        expected.some((name, index) => name !== actual[index])
      )
        return false;
    } else if (profileValue(profile, field) !== (patch[field] ?? '')) return false;
  }
  return true;
}

function patchConflictsWithLatest(
  latest: BusinessProfile,
  patch: ReturnType<typeof serializeBusinessProfilePatch>,
): boolean {
  if (!patch) return false;
  for (const field of Object.keys(patch) as (keyof BusinessProfileDraft)[]) {
    if (field === 'capabilities') {
      const original = profileValue(baseline.value, field) as string[];
      const current = profileValue(latest, field) as string[];
      const expected = (patch.capabilities ?? []).map(({ name }) => name);
      if (
        JSON.stringify(current) !== JSON.stringify(original) &&
        JSON.stringify(current) !== JSON.stringify(expected)
      )
        return true;
    } else {
      const original = profileValue(baseline.value, field);
      const current = profileValue(latest, field);
      if (current !== original && current !== (patch[field] ?? '')) return true;
    }
  }
  return false;
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return;
  if (draft.value.website.trim() && !websiteUrl(draft.value.website)) {
    errors.value.website = 'Enter a valid HTTP or HTTPS website address.';
    error.value = 'Check the website address before saving.';
    return;
  }
  const patch = serializeBusinessProfilePatch(baseline.value, draft.value as BusinessProfileDraft);
  if (!patch) return;
  errors.value = {};
  error.value = '';
  status.value = '';
  try {
    const saved = await save.mutateAsync(patch);
    if (!responseHasIdentity(saved)) {
      uncertain.value = true;
      error.value =
        'The response did not confirm this Business. Refresh saved data before continuing.';
      return;
    }
    baseline.value = saved;
    state.accept(createBusinessProfileDraft(saved));
    emit('update:visible', false);
  } catch (failure) {
    if (failure instanceof ApiError && failure.status < 500) {
      applyErrors(failure.fields);
      error.value =
        failure.status === 409
          ? 'Business details changed on the server. Refresh saved data before applying your draft.'
          : failure.message;
      return;
    }
    uncertain.value = true;
    error.value =
      'The save outcome is uncertain. Your draft is still here. Refresh saved data before saving again.';
  }
}

async function refreshSaved(): Promise<void> {
  if (pending.value) return;
  error.value = '';
  status.value = '';
  refreshing.value = true;
  try {
    const result = await business.refetch();
    if (result.isError || !result.data || !responseHasIdentity(result.data)) {
      error.value = 'Saved Business data could not be confirmed. Your draft is unchanged.';
      return;
    }
    const patch = serializeBusinessProfilePatch(
      baseline.value,
      draft.value as BusinessProfileDraft,
    );
    if (patchMatches(result.data, patch)) {
      baseline.value = result.data;
      state.accept(createBusinessProfileDraft(result.data));
      uncertain.value = false;
      status.value = 'The saved Business details match your changes.';
      return;
    }
    if (patchConflictsWithLatest(result.data, patch)) {
      error.value =
        'The Business fields you changed also changed on the server. Your draft remains here; cancel and reopen to review the saved values.';
      return;
    }
    const submittedDraft = structuredClone(toRaw(draft.value));
    const changedFields = patch ? (Object.keys(patch) as (keyof BusinessProfileDraft)[]) : [];
    const latestDraft = createBusinessProfileDraft(result.data);
    state.updateBaseline(latestDraft);
    for (const field of changedFields) {
      if (field === 'capabilities') latestDraft.capabilities = submittedDraft.capabilities;
      else latestDraft[field] = submittedDraft[field];
    }
    state.draft.value = latestDraft;
    baseline.value = result.data;
    uncertain.value = false;
    status.value =
      'Saved Business data refreshed. Your draft is unchanged; review it before saving again.';
  } finally {
    refreshing.value = false;
  }
}

function cancel(): void {
  close();
}
</script>

<template>
  <Dialog
    :visible="visible"
    modal
    :draggable="false"
    header="Business details"
    :style="{ width: 'min(38rem, calc(100vw - 2rem))' }"
    @update:visible="(next: boolean) => (next ? undefined : close())"
  >
    <form class="business-form" novalidate @submit.prevent="submit">
      <p v-if="error" class="form-message form-message--error" role="alert">{{ error }}</p>
      <p v-if="status" role="status">{{ status }}</p>
      <div class="field">
        <label for="business-name">Business name</label>
        <InputText
          id="business-name"
          v-model="draft.name"
          :disabled="pending"
          autocomplete="organization"
          aria-describedby="business-name-error"
          :aria-invalid="Boolean(errors.name)"
          @input="errors.name = ''"
        />
        <FieldFeedback id="business-name-error" :message="errors.name || ''" />
      </div>
      <div class="field">
        <label for="business-tagline">Tagline</label>
        <InputText
          id="business-tagline"
          v-model="draft.tagline"
          :disabled="pending"
          aria-describedby="business-tagline-error"
          :aria-invalid="Boolean(errors.tagline)"
          @input="errors.tagline = ''"
        />
        <FieldFeedback id="business-tagline-error" :message="errors.tagline || ''" />
      </div>
      <div class="field">
        <label for="business-website">Website</label>
        <InputText
          id="business-website"
          v-model="draft.website"
          :disabled="pending"
          type="url"
          autocomplete="url"
          aria-describedby="business-website-error"
          :aria-invalid="Boolean(errors.website)"
          @input="errors.website = ''"
        />
        <FieldFeedback id="business-website-error" :message="errors.website || ''" />
      </div>
      <div class="field">
        <label for="business-location">Location</label>
        <InputText
          id="business-location"
          v-model="draft.location"
          :disabled="pending"
          autocomplete="address-level2"
          aria-describedby="business-location-error"
          :aria-invalid="Boolean(errors.location)"
          @input="errors.location = ''"
        />
        <FieldFeedback id="business-location-error" :message="errors.location || ''" />
      </div>
      <div class="field">
        <label for="business-description">About your business</label>
        <Textarea
          id="business-description"
          v-model="draft.description"
          :disabled="pending"
          rows="5"
          aria-describedby="business-description-error"
          :aria-invalid="Boolean(errors.description)"
          @input="errors.description = ''"
        />
        <FieldFeedback id="business-description-error" :message="errors.description || ''" />
      </div>
      <div class="field">
        <label for="business-capabilities">Capabilities</label>
        <Textarea
          id="business-capabilities"
          v-model="capabilityText"
          :disabled="pending"
          rows="4"
          aria-describedby="business-capabilities-help business-capabilities-error"
          :aria-invalid="Boolean(errors.capabilities)"
          @input="errors.capabilities = ''"
        />
        <small id="business-capabilities-help">Enter one capability per line.</small>
        <FieldFeedback id="business-capabilities-error" :message="errors.capabilities || ''" />
      </div>
      <div class="actions">
        <Button type="submit" label="Save changes" :disabled="!canSubmit" :loading="pending" />
        <Button
          type="button"
          label="Cancel"
          severity="secondary"
          :disabled="pending || !state.dirty.value"
          @click="cancel"
        />
        <Button
          v-if="uncertain"
          type="button"
          label="Refresh saved data"
          severity="secondary"
          :disabled="pending"
          @click="refreshSaved"
        />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.business-form {
  display: grid;
  gap: var(--space-4);
  max-height: min(70vh, 44rem);
  overflow-y: auto;
  padding-right: var(--space-1);
}
.field {
  display: grid;
  gap: var(--space-2);
}
.field label {
  font-weight: 600;
}
.field small {
  color: var(--color-text-muted);
}
.field textarea {
  min-height: 6rem;
  padding: var(--space-3);
  font: inherit;
  line-height: 1.5;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
  resize: vertical;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding-bottom: var(--space-1);
}
.form-message--error {
  color: var(--color-danger-text);
}
</style>
