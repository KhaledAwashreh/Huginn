<script setup lang="ts">
import { computed, inject, onScopeDispose, ref, watch } from 'vue';
import { matchedRouteKey, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Textarea from 'primevue/textarea';
import Dialog from 'primevue/dialog';
import { Mail } from '@lucide/vue';
import { ApiError } from '../../../api/apiError';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ActionFeedback from '../../../shared/ui/ActionFeedback.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import { useDirtyDraft } from '../../../shared/forms/useDirtyDraft';
import IdealClientProfileFields from '../../configuration/ideal-client-profiles/components/IdealClientProfileFields.vue';
import {
  createIdealClientProfileDraft,
  type IdealClientProfileDraft,
} from '../../configuration/ideal-client-profiles/forms/idealClientProfileDraft';
import { icpSelectionConflicts } from '../../configuration/ideal-client-profiles/forms/icpSelectionConflicts';
import { useAccountSecurity } from '../../account-lifecycle/composables/useAccountSecurity';
import { openSettingsKey } from '../../../shared/navigation/settingsSections';
import { useBusinessSetup } from '../composables/useBusinessSetup';
import { businessSetupDraft } from '../forms/businessSetupDraft';

const { profile, save, identity } = useBusinessSetup();
const security = useAccountSecurity();
const openSettings = inject(openSettingsKey, undefined);
const { draft, dirty, updateBaseline, accept, canLeave } = useDirtyDraft(businessSetupDraft());
const icpDraft = ref<IdealClientProfileDraft | null>(null);
const error = ref('');
const notice = ref('');
const validation = ref<ApiError | null>(null);
const icpMissing = ref(false);
const icpValidation = computed(() =>
  validation.value
    ? new ApiError(
        validation.value.status,
        validation.value.code,
        validation.value.message,
        validation.value.fields
          .filter((item) => item.path[0] === 'ideal_client_profile')
          .map((item) => ({ ...item, path: item.path.slice(1) })),
      )
    : null,
);
watch(dirty, (changed) => {
  if (changed) notice.value = '';
});
const pending = computed(() => save.isPending.value);
watch(
  identity,
  () => {
    accept(businessSetupDraft());
    icpDraft.value = null;
    error.value = notice.value = '';
    validation.value = null;
    icpMissing.value = false;
  },
  { flush: 'sync' },
);
watch(
  profile.data,
  (saved) => {
    if (saved) updateBaseline(businessSetupDraft(saved));
  },
  { immediate: true },
);
const icpSummary = computed(() => {
  const icp = draft.value.ideal_client_profile;
  if (!icp) return 'Choose industries, company sizes, countries and exclusions.';
  return (
    [
      ...icp.industries.map((item) => item.name),
      ...icp.company_sizes.map((item) => `${item.band} employees`),
      ...icp.geographies.map((item) => item.value),
      ...(icp.exclusions.length ? [`${icp.exclusions.length} exclusions`] : []),
    ].join(' · ') || 'All industries, company sizes and locations.'
  );
});
const icpConflicts = computed(() => (icpDraft.value ? icpSelectionConflicts(icpDraft.value) : []));
function openIcp() {
  notice.value = '';
  icpDraft.value = createIdealClientProfileDraft(draft.value.ideal_client_profile);
}
function applyIcp() {
  if (!icpDraft.value?.name.trim() || icpConflicts.value.length) return;
  draft.value.ideal_client_profile = createIdealClientProfileDraft(icpDraft.value);
  icpDraft.value = null;
  icpMissing.value = false;
}
const unappliedIcpChanges = computed(
  () =>
    icpDraft.value !== null &&
    JSON.stringify(icpDraft.value) !==
      JSON.stringify(createIdealClientProfileDraft(draft.value.ideal_client_profile)),
);
function beforeUnload(event: BeforeUnloadEvent) {
  if (!unappliedIcpChanges.value) return;
  event.preventDefault();
  event.returnValue = '';
}
window.addEventListener('beforeunload', beforeUnload);
onScopeDispose(() => window.removeEventListener('beforeunload', beforeUnload));
async function canClose() {
  if (pending.value) return false;
  if (unappliedIcpChanges.value)
    return window.confirm('Discard your unsaved ICP and profile changes?');
  return canLeave();
}
if (inject(matchedRouteKey, null)) {
  onBeforeRouteLeave(canClose);
  onBeforeRouteUpdate(canClose);
}
async function submit() {
  if (pending.value) return;
  error.value = notice.value = '';
  validation.value = null;
  const value = draft.value;
  if (!value.ideal_client_profile) {
    icpMissing.value = true;
    return;
  }
  if (
    ![value.business_name, value.your_name, value.service_description].every((item) => item.trim())
  ) {
    error.value = 'Complete each required field before saving.';
    return;
  }
  const requestedIdentity = identity.value;
  try {
    const saved = await save.mutateAsync({
      business_name: value.business_name.trim(),
      your_name: value.your_name.trim(),
      service_description: value.service_description.trim(),
      ideal_client_profile: createIdealClientProfileDraft(value.ideal_client_profile),
    });
    if (requestedIdentity !== identity.value) return;
    accept(businessSetupDraft(saved));
    notice.value = 'Profile saved.';
  } catch (failure) {
    if (requestedIdentity !== identity.value) return;
    if (failure instanceof ApiError && failure.status < 500) {
      validation.value = failure;
      error.value = failure.message;
      if (failure.fields.some((item) => item.path[0] === 'ideal_client_profile')) openIcp();
    } else
      error.value =
        'The save could not be confirmed. Your draft is still here. Try Save profile again.';
  }
}
function fieldError(field: string) {
  return validation.value?.fields.find((item) => item.path[0] === field)?.message;
}
</script>

<template>
  <div class="profile-page">
    <PageHeader title="Profile" description="Tell us what you do and who you want to work with." />
    <LoadingState
      v-if="profile.isPending.value && !profile.data.value"
      message="Loading your profile…"
    />
    <ErrorState
      v-else-if="profile.isError.value && !profile.data.value"
      :message="
        profile.error.value instanceof ApiError && profile.error.value.status === 409
          ? profile.error.value.message +
            ' Contact support to resolve multiple saved setup records.'
          : 'Your profile could not be loaded.'
      "
    >
      <Button
        v-if="!(profile.error.value instanceof ApiError && profile.error.value.status === 409)"
        label="Retry profile"
        :disabled="profile.isFetching.value"
        @click="profile.refetch()"
      />
    </ErrorState>
    <form v-else-if="profile.data.value" class="profile-form" @submit.prevent="submit">
      <ErrorState
        v-if="profile.isError.value"
        message="Your profile could not be refreshed. Your draft is still here."
      >
        <Button
          label="Retry profile"
          :disabled="profile.isFetching.value"
          @click="profile.refetch()"
        />
      </ErrorState>
      <section class="profile-section" aria-labelledby="business-heading">
        <div class="section-heading">
          <span class="step" aria-hidden="true">1</span>
          <div>
            <h2 id="business-heading">Your business</h2>
            <p>A little about you and the service you offer.</p>
          </div>
        </div>
        <div class="profile-fields">
          <div class="field full">
            <label for="business-name">Business name <span>(required)</span></label>
            <InputText
              id="business-name"
              v-model="draft.business_name"
              autocomplete="organization"
              required
              :disabled="pending"
              :aria-invalid="Boolean(fieldError('business_name'))"
              :aria-describedby="fieldError('business_name') ? 'business-name-error' : undefined"
            />
            <small
              v-if="fieldError('business_name')"
              id="business-name-error"
              class="field-error"
              >{{ fieldError('business_name') }}</small
            >
          </div>
          <div class="field">
            <label for="your-name">Your name <span>(required)</span></label>
            <InputText
              id="your-name"
              v-model="draft.your_name"
              autocomplete="name"
              :aria-describedby="
                fieldError('your_name') ? 'your-name-help your-name-error' : 'your-name-help'
              "
              required
              :disabled="pending"
              :aria-invalid="Boolean(fieldError('your_name'))"
            />
            <small id="your-name-help">First and last name.</small>
            <small v-if="fieldError('your_name')" id="your-name-error" class="field-error">{{
              fieldError('your_name')
            }}</small>
          </div>
          <div class="field">
            <label for="profile-email">Account email</label>
            <InputText
              id="profile-email"
              :model-value="security.data.value?.account_email ?? ''"
              :placeholder="security.isPending.value ? 'Loading email…' : 'Email unavailable'"
              readonly
              aria-describedby="profile-email-help"
            />
            <small id="profile-email-help"
              >Used for sign-in, recovery, and weekly recommendations.</small
            >
            <Button
              v-if="openSettings"
              type="button"
              label="Change email"
              severity="secondary"
              text
              @click="openSettings('security')"
            />
          </div>
          <div class="field full">
            <label for="service-description"
              >Tell us about your service <span>(required)</span></label
            >
            <Textarea
              id="service-description"
              v-model="draft.service_description"
              rows="5"
              required
              :disabled="pending"
              :aria-invalid="Boolean(fieldError('service_description'))"
              :aria-describedby="
                fieldError('service_description')
                  ? 'service-description-help service-description-error'
                  : 'service-description-help'
              "
            />
            <small id="service-description-help"
              >What do you help clients with? Describe the work you sell and the problems you
              solve.</small
            >
            <small
              v-if="fieldError('service_description')"
              id="service-description-error"
              class="field-error"
              >{{ fieldError('service_description') }}</small
            >
          </div>
        </div>
      </section>
      <section class="profile-section" aria-labelledby="icp-heading">
        <div class="section-heading">
          <span class="step" aria-hidden="true">2</span>
          <div>
            <h2 id="icp-heading">Your ideal clients</h2>
            <p>Keep your ICP focused on the companies you want to work with.</p>
          </div>
        </div>
        <div class="icp-summary">
          <div>
            <h3>{{ draft.ideal_client_profile?.name || 'Who is your ideal client?' }}</h3>
            <p>{{ icpSummary }}</p>
          </div>
          <Button
            :label="draft.ideal_client_profile ? 'Edit ICP' : 'Define your ICP'"
            :disabled="pending"
            severity="secondary"
            @click="openIcp"
          />
        </div>
        <p v-if="icpMissing" class="field-error" role="alert">
          Define your ICP before saving your profile.
        </p>
      </section>
      <section class="profile-section delivery">
        <Mail :size="24" aria-hidden="true" />
        <div>
          <h2>Weekly recommendations</h2>
          <p v-if="security.data.value?.email_verified">
            Weekly recommendations use your saved service and ICP when enabled.
          </p>
          <p v-else-if="security.data.value">
            Verify your email in Security before your first delivery.
          </p>
        </div>
      </section>
      <div class="profile-footer">
        <div class="profile-save-state">
          <p v-if="!notice && !error && !pending">
            {{ dirty ? 'You have unsaved changes.' : 'Your saved profile is up to date.' }}
          </p>
          <ActionFeedback :success="notice" :error="error" />
        </div>
        <Button
          type="submit"
          :label="pending ? 'Saving…' : 'Save profile'"
          :loading="pending"
          :disabled="pending || !dirty"
        />
      </div>
    </form>
    <Dialog
      :visible="icpDraft !== null"
      modal
      :draggable="false"
      header="Your ICP definition"
      :style="{ width: 'min(46rem, calc(100vw - 2rem))' }"
      @update:visible="
        (next: boolean) => {
          if (!next) icpDraft = null;
        }
      "
    >
      <form v-if="icpDraft" class="icp-form" @submit.prevent="applyIcp">
        <p>These changes are saved when you save your profile.</p>
        <IdealClientProfileFields v-model="icpDraft" :validation="icpValidation" />
        <p v-for="conflict in icpConflicts" :key="conflict" class="field-error" role="alert">
          {{ conflict }}
        </p>
        <div class="icp-actions">
          <Button label="Cancel ICP changes" severity="secondary" @click="icpDraft = null" /><Button
            type="submit"
            label="Apply ICP"
            :disabled="!icpDraft.name.trim() || icpConflicts.length > 0"
          />
        </div>
      </form>
    </Dialog>
  </div>
</template>
<style scoped>
.profile-page {
  width: min(100%, 50rem);
  display: grid;
  gap: var(--space-6);
  margin: 0 auto;
}
.profile-form {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  overflow: hidden;
}
.profile-section {
  padding: var(--space-6);
}
.profile-section + .profile-section {
  border-top: 1px solid var(--color-border);
}
.section-heading {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  margin-bottom: var(--space-5);
}
.step {
  display: grid;
  place-items: center;
  flex: none;
  width: 1.75rem;
  height: 1.75rem;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}
h2,
h3,
p {
  margin: 0;
  overflow-wrap: anywhere;
}
h2 {
  font-size: 1.1875rem;
  line-height: 1.4;
}
h3 {
  font-size: 1rem;
}
.section-heading p,
.icp-summary p,
.delivery p {
  margin-top: var(--space-1);
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
.profile-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
}
.field {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
}
.full {
  grid-column: 1/-1;
}
label {
  font-weight: 600;
  font-size: 0.875rem;
}
label span,
small {
  font-weight: 400;
  color: var(--color-text-muted);
}
.field :deep(input),
.field :deep(textarea) {
  width: 100%;
}
.field :deep(textarea) {
  resize: vertical;
  line-height: 1.65;
}
.icp-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface-muted);
}
.icp-summary > div {
  min-width: 0;
}
.icp-summary :deep(button) {
  flex: none;
}
.delivery {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
}
.delivery svg {
  color: var(--color-primary);
  flex: none;
}
.delivery h2 {
  font-size: 1rem;
}
.profile-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-5) var(--space-6);
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-muted);
}
.profile-footer p {
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}
.profile-save-state {
  min-width: 0;
}
.profile-footer :deep(button[type='submit']) {
  flex-shrink: 0;
}
.field-error {
  color: var(--color-danger-text);
}
.icp-form {
  display: grid;
  gap: var(--space-5);
}
.icp-form > p {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
.icp-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--space-2);
}
@media (max-width: 600px) {
  .profile-section {
    padding: var(--space-5);
  }
  .profile-fields {
    grid-template-columns: minmax(0, 1fr);
  }
  .icp-summary {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--space-3);
  }
  .profile-footer {
    padding: var(--space-5);
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
