<script setup lang="ts">
import { computed, ref, toRaw } from 'vue';
import { onBeforeRouteLeave, onBeforeRouteUpdate, RouterLink } from 'vue-router';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { ApiError } from '../../../../api/apiError';
import type { FieldError } from '../../../../api/apiError';
import { useDirtyDraft } from '../../../../shared/forms/useDirtyDraft';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import {
  COUNTRY_OPTIONS,
  callingCodeForCountry,
} from '../../../account-lifecycle/forms/signupDraft';
import { useAccount } from '../composables/useAccount';
import { createAccountDraft, type AccountResponse, type AccountDraft } from '../forms/accountDraft';
import { serializeAccountPatch } from '../forms/serializeAccountPatch';
import PasswordSecurityForm from './PasswordSecurityForm.vue';
import RecoveryEmailEnrollment from '../../../account-lifecycle/components/RecoveryEmailEnrollment.vue';
import { useAccountSecurity } from '../../../account-lifecycle/composables/useAccountSecurity';
import { useSession } from '../../../session/composables/useSession';

const props = defineProps<{ account: AccountResponse }>();
const baseline = ref(props.account);
const {
  draft: draftRef,
  dirty,
  updateBaseline,
  accept,
  reset,
  canLeave,
} = useDirtyDraft(createAccountDraft(props.account));
const draft = computed(() => draftRef.value);
const { save, account: accountQuery } = useAccount();
const session = useSession();
const security = useAccountSecurity();
const pending = computed(() => save.isPending.value);
const errors = ref<Record<string, string>>({});
const message = ref('');
const refreshMessage = ref('');
const uncertainOutcome = ref(false);
const matchingCallingCode = computed(() => {
  const code = callingCodeForCountry(draft.value.country_of_residence);
  return code && draft.value.phone_number.startsWith(`+${code}`) ? `+${code}` : '';
});
const fieldNames = [
  'first_name',
  'last_name',
  'email',
  'phone_number',
  'country_of_residence',
  'timezone',
] as const;
function applyErrors(fields: FieldError[]): void {
  for (const field of fields) {
    const key = field.path[0];
    if (typeof key === 'string' && fieldNames.includes(key as (typeof fieldNames)[number]))
      errors.value[key] = field.message;
  }
}
function setServerBaseline(next: AccountResponse): void {
  baseline.value = next;
  updateBaseline(createAccountDraft(next));
}
function refreshBaselinePreservingDraft(next: AccountResponse): void {
  const retainedDraft = structuredClone(toRaw(draftRef.value));
  baseline.value = next;
  updateBaseline(createAccountDraft(next));
  draftRef.value = retainedDraft;
}
function cancel(): void {
  errors.value = {};
  message.value = '';
  reset();
}
async function refreshSaved(): Promise<void> {
  refreshMessage.value = '';
  const result = await accountQuery.refetch();
  if (!result.isError && result.data) {
    refreshBaselinePreservingDraft(result.data);
    uncertainOutcome.value = false;
    message.value = '';
  } else refreshMessage.value = 'Saved data could not be refreshed. Your draft is still here.';
}
async function submit(): Promise<void> {
  if (pending.value) return;
  const patch = serializeAccountPatch(baseline.value, toRaw(draft.value) as AccountDraft);
  if (!Object.keys(patch).length) return;
  errors.value = {};
  message.value = '';
  try {
    const saved = await save.mutateAsync(patch);
    setServerBaseline(saved);
    accept(createAccountDraft(saved));
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
  <div class="configuration-form">
    <section aria-labelledby="personal-title">
      <h2 id="personal-title">Personal details</h2>
      <form class="fields" @submit.prevent="submit">
        <label for="account-first-name">First name</label
        ><InputText
          id="account-first-name"
          v-model="draft.first_name"
          autocomplete="given-name"
          required
          :disabled="pending"
          :aria-invalid="Boolean(errors.first_name)"
          aria-describedby="account-first-name-error"
          @input="errors.first_name = ''"
        /><FieldFeedback id="account-first-name-error" :message="errors.first_name || ''" />
        <label for="account-last-name">Last name</label
        ><InputText
          id="account-last-name"
          v-model="draft.last_name"
          autocomplete="family-name"
          required
          :disabled="pending"
          :aria-invalid="Boolean(errors.last_name)"
          aria-describedby="account-last-name-error"
          @input="errors.last_name = ''"
        /><FieldFeedback id="account-last-name-error" :message="errors.last_name || ''" />
        <label for="account-email">Contact email</label
        ><InputText
          id="account-email"
          v-model="draft.email"
          type="email"
          autocomplete="email"
          required
          :disabled="pending"
          :aria-invalid="Boolean(errors.email)"
          aria-describedby="account-email-error"
          @input="errors.email = ''"
        /><FieldFeedback id="account-email-error" :message="errors.email || ''" />
        <label for="account-country">Country of residence</label>
        <select
          id="account-country"
          v-model="draft.country_of_residence"
          autocomplete="country"
          required
          :disabled="pending"
          :aria-invalid="Boolean(errors.country_of_residence)"
          aria-describedby="account-country-error"
          @change="errors.country_of_residence = ''"
        >
          <option value="" disabled>Select a country</option>
          <option
            v-if="
              draft.country_of_residence &&
              !COUNTRY_OPTIONS.some((country) => country.code === draft.country_of_residence)
            "
            :value="draft.country_of_residence"
          >
            {{ draft.country_of_residence }} (current saved country)
          </option>
          <option v-for="country in COUNTRY_OPTIONS" :key="country.code" :value="country.code">
            {{ country.name }}
          </option></select
        ><FieldFeedback id="account-country-error" :message="errors.country_of_residence || ''" />
        <label for="account-phone">Phone number (E.164)</label
        ><InputText
          id="account-phone"
          v-model="draft.phone_number"
          type="tel"
          autocomplete="tel"
          inputmode="tel"
          pattern="\+[1-9][0-9]{1,14}"
          required
          :disabled="pending"
          :aria-invalid="Boolean(errors.phone_number)"
          aria-describedby="account-phone-error"
          @input="errors.phone_number = ''"
        />
        <small v-if="matchingCallingCode"
          >Calling code for this country: {{ matchingCallingCode }}. The complete saved number is
          shown to preserve its exact E.164 value.</small
        >
        <small v-else
          >The saved number keeps its own international prefix when you change residence
          country.</small
        ><FieldFeedback id="account-phone-error" :message="errors.phone_number || ''" />
        <label for="account-timezone">Timezone (optional)</label
        ><InputText
          id="account-timezone"
          v-model="draft.timezone"
          autocomplete="off"
          placeholder="Europe/London"
          :disabled="pending"
          :aria-invalid="Boolean(errors.timezone)"
          aria-describedby="account-timezone-error"
          @input="errors.timezone = ''"
        /><small>Leave blank to clear your timezone.</small
        ><FieldFeedback id="account-timezone-error" :message="errors.timezone || ''" />
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
          />
        </div>
      </form>
      <Button
        v-if="uncertainOutcome"
        type="button"
        label="Refresh saved data"
        severity="secondary"
        @click="refreshSaved"
      />
      <p v-if="refreshMessage" role="status">{{ refreshMessage }}</p>
    </section>
    <PasswordSecurityForm />
    <section class="security" aria-labelledby="account-security-title">
      <h2 id="account-security-title">Account security</h2>
      <p>
        Your contact email is used for profile communication. Recovery email is a separate verified
        address used for password recovery.
      </p>
      <p v-if="security.data.value">
        Username: <strong>{{ security.data.value.username }}</strong>
      </p>
      <RecoveryEmailEnrollment />
    </section>
  </div>
</template>
<style scoped>
.configuration-form {
  display: grid;
  gap: var(--space-8);
  max-width: 52rem;
}
.fields {
  display: grid;
  gap: var(--space-2);
  max-width: 36rem;
}
.fields label {
  font-weight: 600;
}
.fields select {
  min-height: 2.75rem;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
  font: inherit;
}
.fields small {
  color: var(--color-text-muted);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.security {
  padding: var(--space-6);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
}
h2 {
  margin-top: 0;
}
</style>
