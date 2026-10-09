<script setup lang="ts">
import PageHeader from '../../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import AccountForm from '../components/AccountForm.vue';
import { useAccount } from '../composables/useAccount';
const { account } = useAccount();
</script>
<template>
  <div class="page">
    <PageHeader
      title="Account"
      description="Update personal contact details and account security."
    />
    <LoadingState
      v-if="account.isPending.value && !account.data.value"
      message="Loading account…"
    />
    <ErrorState
      v-else-if="account.isError.value && !account.data.value"
      message="Account details could not be loaded. Reload before trying again."
    />
    <AccountForm v-else-if="account.data.value" :account="account.data.value" />
  </div>
</template>
<style scoped>
.page {
  display: grid;
  gap: var(--space-6);
}
</style>
