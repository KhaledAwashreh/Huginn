<script setup lang="ts">
import { nextTick, ref } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { ApiError } from '../../../api/apiError';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import FieldFeedback from '../../../shared/ui/FieldFeedback.vue';
import { forgotPassword } from '../api/forgotPassword';

const router = useRouter();
const email = ref('');
const pending = ref(false);
const message = ref('');

async function submit(): Promise<void> {
  if (pending.value) return;
  const input = document.getElementById('forgot-email') as HTMLInputElement | null;
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
  try {
    await forgotPassword({ email: trimmedEmail });
    await router.push({
      name: 'check-email',
      state: { email: trimmedEmail, purpose: 'reset' },
    });
  } catch (error) {
    message.value =
      error instanceof ApiError && (error.status === 429 || error.status === 403)
        ? error.message
        : 'The recovery request could not be completed. Check your connection and try again.';
    if (error instanceof ApiError && error.status === 422 && error.fields.length) {
      message.value = error.fields[0]?.message ?? 'Enter a valid email address.';
      await nextTick();
      input?.focus();
    }
  } finally {
    pending.value = false;
  }
}
</script>
<template>
  <main class="auth-page">
    <section class="auth-card">
      <PageHeader
        title="Forgot password"
        description="Enter the email address you used for your account. If it matches an eligible account, a recovery message will arrive."
      />
      <form class="form-stack" novalidate @submit.prevent="submit">
        <div class="field-group">
          <label for="forgot-email">Email</label>
          <InputText
            id="forgot-email"
            v-model="email"
            type="email"
            autocomplete="email"
            required
            :disabled="pending"
            :aria-invalid="Boolean(message)"
            aria-describedby="forgot-email-error"
            @input="message = ''"
          />
          <FieldFeedback id="forgot-email-error" :message="message" />
        </div>
        <Button type="submit" label="Request reset link" :loading="pending" :disabled="pending" />
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
