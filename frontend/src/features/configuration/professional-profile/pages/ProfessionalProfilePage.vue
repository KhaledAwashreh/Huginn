<script setup lang="ts">
import PageHeader from '../../../../shared/ui/PageHeader.vue';
import LoadingState from '../../../../shared/ui/LoadingState.vue';
import ErrorState from '../../../../shared/ui/ErrorState.vue';
import ProfessionalProfileForm from '../components/ProfessionalProfileForm.vue';
import { useProfessionalProfile } from '../composables/useProfessionalProfile';
const { profile } = useProfessionalProfile();
</script>
<template>
  <div class="page">
    <PageHeader
      title="Professional profile"
      description="Keep your skills, experience, and previous projects up to date."
    />
    <LoadingState
      v-if="profile.isPending.value && !profile.data.value"
      message="Loading professional profile…"
    />
    <ErrorState
      v-else-if="profile.isError.value && !profile.data.value"
      message="Professional profile could not be loaded. Reload before trying again."
    />
    <ProfessionalProfileForm v-else-if="profile.data.value" :profile="profile.data.value" />
  </div>
</template>
<style scoped>
.page {
  display: grid;
  gap: var(--space-6);
}
</style>
