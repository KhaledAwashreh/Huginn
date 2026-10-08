<script setup lang="ts">
import { nextTick, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { ApiError } from '../../../api/apiError';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import FieldFeedback from '../../../shared/ui/FieldFeedback.vue';
import { resendVerification } from '../api/resendVerification';
import { forgotPassword } from '../api/forgotPassword';

const state: unknown = window.history.state;
const saved = typeof state === 'object' && state !== null ? (state as Record<string, unknown>) : {};
const email = ref(typeof saved.email === 'string' ? saved.email : '');
const reset = saved.purpose === 'reset';
const pending = ref(false);
const message = ref('');
const receipt = ref('');

async function submit(): Promise<void> {
  if (pending.value) return;
  const input = document.getElementById('receipt-email') as HTMLInputElement | null;
  const trimmedEmail = email.value.trim();
  if (!trimmedEmail) {
    message.value = 'Enter your email address.';
    await nextTick();
    input?.focus();
    return;
  }
  if (!input?.validity.valid) {
    message.value = 'Enter a valid email address.';
    await nextTick();
    input?.focus();
    return;
  }

  pending.value = true;
  message.value = '';
  receipt.value = '';
  try {
    await (reset ? forgotPassword : resendVerification)({ email: trimmedEmail });
    email.value = trimmedEmail;
    receipt.value =
      'If this address matches an eligible account, a message will arrive. Check your spam folder too.';
  } catch (error) {
    message.value =
      error instanceof ApiError && (error.status === 429 || error.status === 403)
        ? error.message
        : reset
          ? 'The recovery request could not be completed. Check your connection and try again.'
          : 'The verification request could not be completed. Check your connection and try again.';
  } finally {
    pending.value = false;
  }
}
</script>
<template>
  <main class="auth-page">
    <section class="auth-card">
      <PageHeader
        title="Check your email"
        :description="
          reset
            ? 'If the address matches an eligible account, a recovery message will arrive.'
            : 'If the address matches an eligible account, a verification message will arrive.'
        "
      />
      <p>
        Open the original email link to continue. Links expire; requesting a new link replaces the
        previous one.
      </p>
      <form class="form-stack" novalidate @submit.prevent="submit">
        <div class="field-group">
          <label for="receipt-email">Email</label>
          <InputText
            id="receipt-email"
            v-model="email"
            type="email"
            autocomplete="email"
            required
            :disabled="pending"
            :aria-invalid="Boolean(message)"
            aria-describedby="receipt-email-error"
            @input="
              message = '';
              receipt = '';
            "
          />
          <FieldFeedback id="receipt-email-error" :message="message" />
        </div>
        <p v-if="receipt" role="status">{{ receipt }}</p>
        <Button
          type="submit"
          :label="reset ? 'Request another reset link' : 'Resend verification link'"
          :loading="pending"
          :disabled="pending"
        />
      </form>
      <p><RouterLink to="/login">Sign in</RouterLink></p>
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
