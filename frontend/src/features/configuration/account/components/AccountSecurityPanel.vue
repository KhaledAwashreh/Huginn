<script setup lang="ts">
import { ref } from 'vue';
import PasswordSecurityForm from './PasswordSecurityForm.vue';
import RecoveryEmailEnrollment from '../../../account-lifecycle/components/RecoveryEmailEnrollment.vue';
const passwordForm = ref<InstanceType<typeof PasswordSecurityForm> | null>(null);
const emailForm = ref<InstanceType<typeof RecoveryEmailEnrollment> | null>(null);
defineExpose({
  canClose: () =>
    (passwordForm.value?.canClose() ?? true) && (emailForm.value?.canClose?.() ?? true),
});
</script>
<template>
  <div class="account-security">
    <PasswordSecurityForm ref="passwordForm" />
    <RecoveryEmailEnrollment ref="emailForm" />
  </div>
</template>
<style scoped>
.account-security {
  display: grid;
  gap: var(--space-8);
  max-width: 52rem;
}
</style>
