<script setup lang="ts">
import PasswordSecurityForm from './PasswordSecurityForm.vue';
import RecoveryEmailEnrollment from '../../../account-lifecycle/components/RecoveryEmailEnrollment.vue';
import { useAccountSecurity } from '../../../account-lifecycle/composables/useAccountSecurity';

const security = useAccountSecurity();
</script>
<template>
  <div class="account-security">
    <PasswordSecurityForm />
    <section class="security" aria-labelledby="account-security-title">
      <h2 id="account-security-title">Recovery</h2>
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
.account-security {
  display: grid;
  gap: var(--space-8);
  max-width: 52rem;
}
.security {
  padding: var(--space-6);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
h2 {
  margin-top: 0;
}
</style>
