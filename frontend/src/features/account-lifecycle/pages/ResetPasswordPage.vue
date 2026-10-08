<script setup lang="ts">
import { reactive, ref, onBeforeUnmount, nextTick, watch } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { ApiError } from '../../../api/apiError';
import PageHeader from '../../../shared/ui/PageHeader.vue';
import FieldFeedback from '../../../shared/ui/FieldFeedback.vue';
import { useProofFragment } from '../composables/useProofFragment';
import { resetPassword } from '../api/resetPassword';
import type { ResetPasswordDraft } from '../forms/resetPasswordDraft';
import { validateLifecyclePassword } from '../forms/resetPasswordDraft';
import { useSession } from '../../session/composables/useSession';
const proof = useProofFragment();
const session = useSession();
const draft = reactive<ResetPasswordDraft>({ new_password: '' });
const pending = ref(false);
const saved = ref(false);
const message = ref('');
const passwordError = ref('');
watch([proof.token, proof.status], ([token, status]) => {
  if (!token && status !== 'invalid') return;
  saved.value = false;
  message.value = '';
  passwordError.value = '';
  draft.new_password = '';
});
onBeforeUnmount(() => {
  draft.new_password = '';
});
async function submit(): Promise<void> {
  if (pending.value || !proof.token.value) return;
  const validationError = validateLifecyclePassword(draft.new_password);
  if (validationError) {
    passwordError.value = validationError;
    message.value = '';
    draft.new_password = '';
    await nextTick();
    document.getElementById('reset-password')?.focus();
    return;
  }
  pending.value = true;
  const submittedToken = proof.token.value;
  message.value = '';
  passwordError.value = '';
  try {
    await resetPassword({ token: submittedToken, new_password: draft.new_password });
    session.clear();
    if (proof.token.value !== submittedToken) return;
    saved.value = true;
    proof.clearProof();
  } catch (error) {
    if (proof.token.value !== submittedToken) return;
    if (error instanceof ApiError)
      passwordError.value =
        error.fields.find((field) => field.path[0] === 'new_password')?.message ?? '';
    if (
      error instanceof ApiError &&
      error.status === 422 &&
      !error.fields.some((field) => field.path[0] === 'new_password')
    ) {
      message.value = 'This link is invalid or expired. Request a new reset link.';
      proof.clearProof();
    } else
      message.value =
        error instanceof ApiError
          ? error.message
          : 'The password could not be saved. Check your connection and try again.';
  } finally {
    draft.new_password = '';
    pending.value = false;
  }
}
</script>
<template>
  <main class="auth-page">
    <section class="auth-card">
      <PageHeader :title="saved ? 'Password saved' : 'Reset password'" />
      <template v-if="saved"
        ><p>Your password was saved and previous sessions were signed out.</p>
        <RouterLink to="/login">Sign in</RouterLink></template
      >
      <template v-else
        ><FieldFeedback :message="message" />
        <form v-if="proof.token.value" class="form-stack" @submit.prevent="submit">
          <div class="field-group">
            <label for="reset-password">New password</label
            ><InputText
              id="reset-password"
              v-model="draft.new_password"
              type="password"
              autocomplete="new-password"
              required
              :aria-invalid="!!passwordError"
              aria-describedby="reset-help reset-error"
              :disabled="pending"
            />
            <p id="reset-help" class="help">
              Use 8 to 16 characters, with a letter, a digit, and punctuation or a symbol.
            </p>
            <FieldFeedback id="reset-error" :message="passwordError" />
          </div>
          <Button type="submit" label="Save password" :loading="pending" :disabled="pending" />
        </form>
        <template v-else
          ><p>Open the original email link, or request a new reset link.</p>
          <RouterLink to="/forgot-password">Request reset link</RouterLink></template
        >
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
