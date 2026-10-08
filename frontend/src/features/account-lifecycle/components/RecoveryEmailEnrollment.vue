<script setup lang="ts">
import { computed, ref } from 'vue';
import Button from 'primevue/button';
import { ApiError } from '../../../api/apiError';
import FieldFeedback from '../../../shared/ui/FieldFeedback.vue';
import LoadingState from '../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../shared/ui/ErrorState.vue';
import { useAccountSecurity } from '../composables/useAccountSecurity';
import { enrollRecoveryEmail } from '../api/enrollRecoveryEmail';
const security = useAccountSecurity();
const pending = ref(false);
const message = ref('');
const receipt = ref('');
const eligible = computed(
  () =>
    security.data.value &&
    !security.data.value.email_verification_required &&
    !security.data.value.email_verified &&
    security.data.value.recovery_email === null,
);
async function enroll(): Promise<void> {
  if (pending.value || !eligible.value) return;
  pending.value = true;
  message.value = '';
  receipt.value = '';
  try {
    await enrollRecoveryEmail();
    receipt.value =
      'If your current contact email is eligible, a verification message will arrive. Check your spam folder too.';
  } catch (error) {
    message.value =
      error instanceof ApiError && (error.status === 429 || error.status === 403)
        ? error.message
        : 'The recovery email request could not be completed. Check your connection and try again.';
  } finally {
    pending.value = false;
  }
}
</script>
<template>
  <section class="security" aria-labelledby="security-title">
    <h2 id="security-title">Account security</h2>
    <p>
      Your profile contact email and verified recovery email serve separate purposes. Changing your
      contact email does not change your recovery destination.
    </p>
    <LoadingState v-if="security.isPending.value" message="Loading account security…" />
    <ErrorState
      v-else-if="security.isError.value"
      message="Account security could not be loaded. Reload before trying again."
    />
    <template v-else-if="security.data.value">
      <p v-if="security.data.value.email_verified">
        Verified recovery email: <strong>{{ security.data.value.recovery_email }}</strong>
      </p>
      <p v-else>
        No verified recovery email. Password recovery is unavailable until you verify an address.
      </p>
      <template v-if="eligible"
        ><p>Send a verification link to your current contact email to enroll it for recovery.</p>
        <Button
          type="button"
          label="Verify contact email for recovery"
          :loading="pending"
          :disabled="pending"
          @click="enroll"
      /></template>
      <FieldFeedback :message="message" />
      <p v-if="receipt" role="status">{{ receipt }}</p>
    </template>
  </section>
</template>
<style scoped>
.security {
  margin-top: var(--space-8);
  padding: var(--space-6);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
p {
  overflow-wrap: anywhere;
}
</style>
