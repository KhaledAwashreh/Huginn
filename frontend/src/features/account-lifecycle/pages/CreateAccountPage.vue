<script setup lang="ts">
import { reactive, ref, onBeforeUnmount, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { ApiError } from '../../../api/apiError';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import FieldFeedback from '../../../shared/ui/FieldFeedback.vue';
import { signup } from '../api/signup';
import {
  COUNTRY_OPTIONS,
  callingCodeForCountry,
  normalizeE164Phone,
  type SignupDraft,
} from '../forms/signupDraft';
import { validateLifecyclePassword } from '../forms/resetPasswordDraft';
const router = useRouter();
const draft = reactive<SignupDraft>({
  username: '',
  password: '',
  first_name: '',
  last_name: '',
  email: '',
  phone_number: '',
  country_of_residence: '',
  timezone: '',
});
const pending = ref(false);
const message = ref('');
const errors = ref<Record<string, string>>({});
const fields = [
  { name: 'username', label: 'Username', autocomplete: 'username', type: 'text', required: true },
  {
    name: 'password',
    label: 'Password',
    autocomplete: 'new-password',
    type: 'password',
    required: true,
  },
  {
    name: 'first_name',
    label: 'First name',
    autocomplete: 'given-name',
    type: 'text',
    required: true,
  },
  {
    name: 'last_name',
    label: 'Last name',
    autocomplete: 'family-name',
    type: 'text',
    required: true,
  },
  { name: 'email', label: 'Email', autocomplete: 'email', type: 'email', required: true },
  {
    name: 'country_of_residence',
    label: 'Country of residence',
    autocomplete: 'country',
    type: 'text',
    required: true,
  },
  { name: 'phone_number', label: 'Phone number', autocomplete: 'tel', type: 'tel', required: true },
  {
    name: 'timezone',
    label: 'Timezone (optional)',
    autocomplete: 'off',
    type: 'text',
    required: false,
  },
] satisfies {
  name: keyof SignupDraft;
  label: string;
  autocomplete: string;
  type: string;
  required: boolean;
}[];
onBeforeUnmount(() => {
  draft.password = '';
});
async function focusFirstInvalid(): Promise<void> {
  await nextTick();
  const firstInvalid = fields.find((field) => errors.value[field.name]);
  if (firstInvalid) document.getElementById(`signup-${firstInvalid.name}`)?.focus();
}
async function submit(): Promise<void> {
  if (pending.value) return;
  const localErrors: Record<string, string> = {};
  for (const field of fields) {
    if (field.required && !draft[field.name].trim())
      localErrors[field.name] = `${field.label} is required.`;
  }
  const passwordError = validateLifecyclePassword(draft.password);
  if (passwordError) localErrors.password = passwordError;
  const phoneNumber = normalizeE164Phone(draft.country_of_residence, draft.phone_number);
  if (!phoneNumber)
    localErrors.phone_number = 'Enter a valid national phone number for this country.';
  const emailInput = document.getElementById('signup-email') as HTMLInputElement | null;
  if (!localErrors.email && !draft.email.trim()) localErrors.email = 'Email is required.';
  if (!localErrors.email && emailInput && !emailInput.validity.valid)
    localErrors.email = 'Enter a valid email address.';
  if (Object.keys(localErrors).length || phoneNumber === null) {
    errors.value = localErrors;
    message.value = '';
    draft.password = '';
    await focusFirstInvalid();
    return;
  }
  pending.value = true;
  message.value = '';
  errors.value = {};
  try {
    const { timezone, ...required } = draft;
    await signup({
      ...required,
      email: draft.email.trim(),
      phone_number: phoneNumber,
      ...(timezone.trim() ? { timezone: timezone.trim() } : {}),
    });
    await router.push({
      name: 'check-email',
      state: { email: draft.email.trim(), purpose: 'verification' },
    });
  } catch (error) {
    message.value =
      error instanceof ApiError && (error.status === 429 || error.status === 403)
        ? error.message
        : 'Account creation could not be completed. Check your details and try again.';
    if (error instanceof ApiError)
      for (const field of error.fields) {
        const key = field.path[0];
        if (typeof key === 'string') errors.value[key] = field.message;
      }
    await focusFirstInvalid();
  } finally {
    draft.password = '';
    pending.value = false;
  }
}
</script>
<template>
  <main class="auth-page">
    <section class="auth-card">
      <PageHeader
        title="Create account"
        description="Verify your email before signing in. All personal fields are required except timezone."
      />
      <form class="form-stack" @submit.prevent="submit">
        <div v-for="field in fields" :key="field.name" class="field-group">
          <label :for="`signup-${field.name}`">{{ field.label }}</label>
          <select
            v-if="field.name === 'country_of_residence'"
            :id="`signup-${field.name}`"
            v-model="draft.country_of_residence"
            :autocomplete="field.autocomplete"
            :required="field.required"
            :disabled="pending"
            :aria-invalid="!!errors[field.name]"
            :aria-describedby="`signup-${field.name}-error`"
            @change="errors.country_of_residence = ''"
          >
            <option value="" disabled>Select a country</option>
            <option v-for="country in COUNTRY_OPTIONS" :key="country.code" :value="country.code">
              {{ country.name }}
            </option>
          </select>
          <div v-else-if="field.name === 'phone_number'" class="phone-fields">
            <InputText
              id="signup-phone-prefix"
              :model-value="
                draft.country_of_residence
                  ? `+${callingCodeForCountry(draft.country_of_residence)}`
                  : ''
              "
              aria-label="Country calling code"
              autocomplete="off"
              readonly
              :disabled="pending"
            />
            <InputText
              id="signup-phone_number"
              v-model="draft.phone_number"
              type="tel"
              autocomplete="tel-national"
              inputmode="numeric"
              pattern="[0-9 -]+"
              required
              :disabled="pending"
              :aria-invalid="!!errors.phone_number"
              aria-describedby="signup-phone_number-help signup-phone_number-error"
              @input="errors.phone_number = ''"
            />
          </div>
          <InputText
            v-else
            :id="`signup-${field.name}`"
            v-model="draft[field.name]"
            :type="field.type"
            :autocomplete="field.autocomplete"
            :required="field.required"
            :disabled="pending"
            :aria-invalid="!!errors[field.name]"
            :aria-describedby="`signup-${field.name}-help signup-${field.name}-error`"
            @input="errors[field.name] = ''"
          />
          <p v-if="field.name === 'password'" :id="`signup-${field.name}-help`" class="help">
            Use 8 to 16 characters, with a letter, a digit, and punctuation or a symbol.
          </p>
          <p
            v-else-if="field.name === 'phone_number'"
            :id="`signup-${field.name}-help`"
            class="help"
          >
            Enter the national number. Spaces and hyphens are allowed; the country prefix is added.
          </p>
          <p v-else-if="field.name === 'timezone'" :id="`signup-${field.name}-help`" class="help">
            Use an IANA timezone, for example Europe/London, or leave blank.
          </p>
          <FieldFeedback :id="`signup-${field.name}-error`" :message="errors[field.name] ?? ''" />
        </div>
        <FieldFeedback :message="message" />
        <Button type="submit" label="Create account" :loading="pending" :disabled="pending" />
      </form>
      <p>Already have an account? <RouterLink to="/login">Sign in</RouterLink></p>
    </section>
  </main>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: var(--space-6);
}
.auth-card {
  width: min(100%, 480px);
  padding: var(--space-8);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
.form-stack,
.field-group {
  display: grid;
  gap: var(--space-2);
}
.form-stack {
  gap: var(--space-5);
}
select,
.phone-fields :deep(input) {
  min-width: 0;
  min-height: 2.75rem;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-control, 0.375rem);
  background: var(--color-surface);
  color: var(--color-text);
  font: inherit;
}
select:focus-visible,
.phone-fields :deep(input:focus-visible) {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
.phone-fields {
  display: grid;
  grid-template-columns: 5rem minmax(0, 1fr);
  gap: var(--space-2);
}
label {
  font-weight: 600;
}
p {
  overflow-wrap: anywhere;
}
.help {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  margin: 0;
}
a {
  color: var(--color-primary);
}
@media (max-width: 400px) {
  .auth-page {
    padding: var(--space-4);
  }
  .auth-card {
    padding: var(--space-5);
  }
}
</style>
