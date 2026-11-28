<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { ApiError } from '../../../api/apiError';
import ActionFeedback from '../../../shared/ui/ActionFeedback.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import { useAccountSecurity } from '../composables/useAccountSecurity';
import { enrollRecoveryEmail } from '../api/enrollRecoveryEmail';
const security = useAccountSecurity();
const pending = ref(false);
const message = ref('');
const receipt = ref('');
const changing = ref(false);
const email = ref('');
const password = ref('');
const eligible = computed(
  () =>
    security.data.value &&
    !security.data.value.email_verification_required &&
    !security.data.value.email_verified,
);
function canClose(): boolean {
  if (pending.value) return false;
  return (
    !changing.value ||
    (!email.value && !password.value) ||
    window.confirm('Discard your unsaved email change?')
  );
}
defineExpose({ canClose });
function closeChange(): void {
  changing.value = false;
  email.value = '';
  password.value = '';
}
async function requestVerification(): Promise<void> {
  if (pending.value || (!changing.value && !eligible.value)) return;
  const isChange = changing.value;
  pending.value = true;
  message.value = '';
  receipt.value = '';
  try {
    await enrollRecoveryEmail(
      isChange ? { email: email.value.trim(), current_password: password.value } : {},
    );
    receipt.value = 'Verification requested. Check your inbox and spam folder for a link.';
    if (isChange) closeChange();
    await security.refetch();
  } catch (error) {
    message.value =
      error instanceof ApiError && [403, 409, 422, 429].includes(error.status)
        ? error.message
        : 'The verification request could not be completed. Try again.';
  } finally {
    password.value = '';
    pending.value = false;
  }
}
</script>
<template>
  <section class="security" aria-labelledby="security-title">
    <h2 id="security-title">Account email</h2>
    <LoadingState v-if="security.isPending.value" message="Loading account security…" />
    <ErrorState
      v-else-if="security.isError.value && !security.data.value"
      message="Account security could not be loaded. Reload before trying again."
    />
    <template v-else-if="security.data.value">
      <p>
        <strong>{{ security.data.value.account_email }}</strong>
      </p>
      <p v-if="security.data.value.email_verified">
        Use this email to sign in, reset your password, and receive weekly recommendations.
      </p>
      <p v-else>Verify your email to enable email sign-in, recovery, and weekly recommendations.</p>
      <p v-if="security.data.value.pending_email">
        Waiting for verification at <strong>{{ security.data.value.pending_email }}</strong
        >.
      </p>
      <form v-if="changing" class="change-form" @submit.prevent="requestVerification">
        <label for="new-account-email">New email</label>
        <InputText
          id="new-account-email"
          v-model="email"
          type="email"
          autocomplete="email"
          required
          :disabled="pending"
        />
        <label for="email-current-password">Current password</label>
        <InputText
          id="email-current-password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          :disabled="pending"
        />
        <div class="actions">
          <Button
            type="submit"
            :label="pending ? 'Requesting verification…' : 'Send verification link'"
            :loading="pending"
            :disabled="pending"
          />
          <Button
            type="button"
            label="Cancel"
            severity="secondary"
            :disabled="pending"
            @click="canClose() && closeChange()"
          />
        </div>
      </form>
      <div v-else class="actions">
        <Button
          v-if="eligible"
          type="button"
          :label="pending ? 'Requesting verification…' : 'Verify current email'"
          :loading="pending"
          :disabled="pending"
          @click="requestVerification"
        />
        <Button
          type="button"
          label="Change email"
          severity="secondary"
          :disabled="pending"
          @click="
            changing = true;
            message = receipt = '';
          "
        />
      </div>
    </template>
    <ActionFeedback :success="receipt" :error="message" />
  </section>
</template>
<style scoped>
.security {
  padding: var(--space-6);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
h2 {
  margin-top: 0;
}
.change-form {
  display: grid;
  gap: var(--space-3);
  max-width: 32rem;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
p {
  overflow-wrap: anywhere;
}
</style>
