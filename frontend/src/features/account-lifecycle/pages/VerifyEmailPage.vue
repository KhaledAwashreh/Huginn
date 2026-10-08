<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { ApiError } from '../../../api/apiError';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import FieldFeedback from '../../../shared/ui/FieldFeedback.vue';
import { useProofFragment } from '../composables/useProofFragment';
import { verifyEmail } from '../api/verifyEmail';
import { resendVerification } from '../api/resendVerification';
const proof = useProofFragment();
const pending = ref(false);
const verified = ref(false);
const email = ref('');
const emailError = ref('');
const message = ref('');
const receipt = ref('');
watch([proof.token, proof.status], ([token, status]) => {
  if (!token && status !== 'invalid') return;
  verified.value = false;
  message.value = '';
  receipt.value = '';
});
async function verify(): Promise<void> {
  if (pending.value || !proof.token.value) return;
  const submittedToken = proof.token.value;
  pending.value = true;
  message.value = '';
  try {
    await verifyEmail({ token: submittedToken });
    if (proof.token.value !== submittedToken) return;
    verified.value = true;
    proof.clearProof();
  } catch (error) {
    if (proof.token.value !== submittedToken) return;
    if (error instanceof ApiError && error.status === 422) {
      message.value = 'This link is invalid or expired. Request a new verification link.';
      proof.clearProof();
    } else
      message.value =
        error instanceof ApiError && (error.status === 429 || error.status === 403)
          ? error.message
          : 'Verification could not be completed. Check your connection and try again.';
  } finally {
    pending.value = false;
  }
}
async function resend(): Promise<void> {
  if (pending.value) return;
  const input = document.getElementById('resend-email') as HTMLInputElement | null;
  const trimmedEmail = email.value.trim();
  if (!trimmedEmail) {
    emailError.value = 'Enter your email address.';
    await nextTick();
    input?.focus();
    return;
  }
  if (!input?.validity.valid) {
    emailError.value = 'Enter a valid email address.';
    await nextTick();
    input?.focus();
    return;
  }
  pending.value = true;
  message.value = '';
  receipt.value = '';
  emailError.value = '';
  try {
    await resendVerification({ email: trimmedEmail });
    email.value = trimmedEmail;
    receipt.value =
      'If this address matches an eligible account, a message will arrive. Check your spam folder too.';
  } catch (error) {
    message.value =
      error instanceof ApiError && (error.status === 429 || error.status === 403)
        ? error.message
        : 'The verification request could not be completed. Check your connection and try again.';
  } finally {
    pending.value = false;
  }
}
</script>
<template>
  <main class="auth-page">
    <section class="auth-card">
      <PageHeader :title="verified ? 'Email verified' : 'Verify email'" />
      <template v-if="verified"
        ><p>Your email is verified. Sign in to continue.</p>
        <RouterLink to="/login">Sign in</RouterLink></template
      >
      <template v-else
        ><FieldFeedback :message="message" />
        <template v-if="proof.token.value"
          ><p>Select Verify email to confirm your address.</p>
          <Button
            type="button"
            label="Verify email"
            :loading="pending"
            :disabled="pending"
            @click="verify"
        /></template>
        <template v-else
          ><p>Open the link from your email to verify your address, or request a new link below.</p>
          <form class="form-stack" novalidate @submit.prevent="resend">
            <div class="field-group">
              <label for="resend-email">Email</label>
              <InputText
                id="resend-email"
                v-model="email"
                type="email"
                autocomplete="email"
                required
                :disabled="pending"
                :aria-invalid="Boolean(emailError)"
                aria-describedby="resend-email-error"
                @input="
                  emailError = '';
                  receipt = '';
                "
              />
              <FieldFeedback id="resend-email-error" :message="emailError" />
            </div>
            <p v-if="receipt" role="status">{{ receipt }}</p>
            <Button
              type="submit"
              label="Resend verification link"
              :loading="pending"
              :disabled="pending"
            />
          </form>
        </template>
      </template>
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
