<script setup lang="ts">
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink } from 'vue-router';
import { computed, ref, toRaw } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { ApiError, type FieldError } from '../../../../api/apiError';
import { useDirtyDraft } from '../../../../shared/forms/useDirtyDraft';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import { useProfessionalProfile } from '../composables/useProfessionalProfile';
import {
  createProfessionalProfileDraft,
  type ProfessionalProfileDraft,
  type ProfessionalProfileResponse,
} from '../forms/professionalProfileDraft';
import { serializeProfessionalProfilePatch } from '../forms/serializeProfessionalProfilePatch';
import { useSession } from '../../../session/composables/useSession';
import ExperienceRows from './ExperienceRows.vue';
import SkillRows from './SkillRows.vue';
import PreviousProjectRows from './PreviousProjectRows.vue';

const props = defineProps<{ profile: ProfessionalProfileResponse }>();
const baseline = ref(props.profile);
const {
  draft: draftRef,
  dirty,
  updateBaseline,
  accept,
  reset,
  canLeave,
} = useDirtyDraft(createProfessionalProfileDraft(props.profile));
const draft = computed(() => draftRef.value);
const { save, profile: profileQuery } = useProfessionalProfile();
const session = useSession();
const pending = computed(() => save.isPending.value);
const errors = ref<Record<string, string>>({});
const message = ref('');
const refreshMessage = ref('');
const uncertainOutcome = ref(false);
function applyErrors(fields: FieldError[]): void {
  for (const field of fields) {
    if (!field.path.length) continue;
    const path = field.path.map(String).join('.');
    if (
      /^(headline|professional_summary|skills\.\d+\.name|experience\.\d+(?:\.(organization|role|summary|start_month|end_month|is_current))?|previous_projects\.\d+(?:\.(name|description))?)$/.test(
        path,
      )
    )
      errors.value[path] = field.message;
  }
}
function setBaseline(next: ProfessionalProfileResponse): void {
  baseline.value = next;
  updateBaseline(createProfessionalProfileDraft(next));
}
function refreshBaselinePreservingDraft(next: ProfessionalProfileResponse): void {
  const retainedDraft = structuredClone(toRaw(draftRef.value));
  baseline.value = next;
  updateBaseline(createProfessionalProfileDraft(next));
  draftRef.value = retainedDraft;
}
function cancel(): void {
  errors.value = {};
  message.value = '';
  reset();
}
async function refreshSaved(): Promise<void> {
  refreshMessage.value = '';
  const result = await profileQuery.refetch();
  if (!result.isError && result.data) {
    refreshBaselinePreservingDraft(result.data);
    uncertainOutcome.value = false;
    message.value = '';
  } else refreshMessage.value = 'Saved data could not be refreshed. Your draft is still here.';
}
function localValidation(value: ProfessionalProfileDraft): Record<string, string> {
  const found: Record<string, string> = {};
  value.skills.forEach((skill, index) => {
    if (!skill.name.trim()) found[`skills.${index}.name`] = 'Enter a skill name.';
  });
  value.experience.forEach((item, index) => {
    if (!item.organization.trim() || !item.role.trim())
      found[`experience.${index}`] = 'Organization and role are required.';
    else if (
      (item.start_month && !/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(item.start_month)) ||
      (item.end_month && !/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(item.end_month))
    )
      found[`experience.${index}`] = 'Use a valid YYYY-MM month.';
    else if (item.is_current && item.end_month)
      found[`experience.${index}`] = 'A current role cannot have an end month.';
    else if (item.start_month && item.end_month && item.end_month < item.start_month)
      found[`experience.${index}`] = 'End month must not precede start month.';
    else if (/^0000-/.test(item.start_month) || /^0000-/.test(item.end_month))
      found[`experience.${index}`] = 'Year must be 0001 or later.';
  });
  value.previous_projects.forEach((item, index) => {
    if (!item.name.trim() || !item.description.trim())
      found[`previous_projects.${index}`] = 'Project name and description are required.';
  });
  return found;
}
async function submit(): Promise<void> {
  if (pending.value) return;
  const validation = localValidation(toRaw(draft.value) as ProfessionalProfileDraft);
  if (Object.keys(validation).length) {
    errors.value = validation;
    message.value = 'Check the highlighted fields.';
    return;
  }
  const patch = serializeProfessionalProfilePatch(
    baseline.value,
    toRaw(draft.value) as ProfessionalProfileDraft,
  );
  if (!Object.keys(patch).length) return;
  errors.value = {};
  message.value = '';
  try {
    const saved = await save.mutateAsync(patch);
    setBaseline(saved);
    accept(createProfessionalProfileDraft(saved));
    uncertainOutcome.value = false;
  } catch (error) {
    if (error instanceof ApiError) {
      applyErrors(error.fields);
      uncertainOutcome.value = error.status >= 500;
      message.value = uncertainOutcome.value
        ? 'The save outcome is unknown. Refresh saved data before deciding to save again.'
        : error.message;
    } else
      message.value =
        'The save outcome is unknown. Refresh saved data before deciding to save again.';
    if (!(error instanceof ApiError)) uncertainOutcome.value = true;
  }
}
onBeforeRouteLeave(() => (pending.value ? false : canLeave()));
onBeforeRouteUpdate(() => (pending.value ? false : canLeave()));
</script>
<template>
  <form class="profile-form" @submit.prevent="submit">
    <section class="group" aria-labelledby="summary-title">
      <h2 id="summary-title">Professional summary</h2>
      <label for="profile-headline">Headline</label
      ><InputText
        id="profile-headline"
        v-model="draft.headline"
        :disabled="pending"
        :aria-invalid="Boolean(errors.headline)"
        aria-describedby="profile-headline-error"
        @input="errors.headline = ''"
      /><FieldFeedback id="profile-headline-error" :message="errors.headline || ''" />
      <label for="profile-summary">Summary</label
      ><textarea
        id="profile-summary"
        v-model="draft.professional_summary"
        rows="5"
        :disabled="pending"
        :aria-invalid="Boolean(errors.professional_summary)"
        aria-describedby="profile-summary-error"
        @input="errors.professional_summary = ''"
      /><FieldFeedback id="profile-summary-error" :message="errors.professional_summary || ''" />
    </section>
    <SkillRows v-model="draft.skills" :errors="errors" :disabled="pending" />
    <ExperienceRows v-model="draft.experience" :errors="errors" :disabled="pending" />
    <PreviousProjectRows v-model="draft.previous_projects" :errors="errors" :disabled="pending" />
    <FieldFeedback :message="message" />
    <RouterLink v-if="!session.isAuthenticated.value" to="/login">Sign in again</RouterLink>
    <div class="actions">
      <Button
        type="submit"
        label="Save changes"
        :loading="pending"
        :disabled="pending || !dirty || uncertainOutcome"
      /><Button
        type="button"
        label="Cancel"
        severity="secondary"
        :disabled="pending || !dirty"
        @click="cancel"
      /><Button
        v-if="uncertainOutcome"
        type="button"
        label="Refresh saved data"
        severity="secondary"
        :disabled="pending"
        @click="refreshSaved"
      />
    </div>
    <p v-if="refreshMessage" role="status">{{ refreshMessage }}</p>
  </form>
</template>
<style scoped>
.profile-form {
  display: grid;
  gap: var(--space-6);
  max-width: 56rem;
}
.group {
  display: grid;
  gap: var(--space-2);
}
.group h2 {
  margin: 0 0 var(--space-2);
}
.group label {
  font-weight: 600;
}
.group textarea {
  min-height: 8rem;
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
}
</style>
