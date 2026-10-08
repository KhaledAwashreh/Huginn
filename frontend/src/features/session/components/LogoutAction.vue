<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import { useSession } from '../composables/useSession';
import { ApiError } from '../../../api/apiError';

const session = useSession();
const router = useRouter();
const pending = ref(false);
const message = ref('');
async function logout(): Promise<void> {
  if (pending.value) return;
  pending.value = true;
  message.value = '';
  try {
    await session.logout();
    await router.replace('/login');
  } catch (error) {
    message.value = error instanceof ApiError ? error.message : 'Sign out failed. Try again.';
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <div class="logout-action">
    <Button
      label="Sign out"
      severity="secondary"
      :disabled="pending"
      :loading="pending"
      @click="logout"
    />
    <span v-if="message" role="alert">{{ message }}</span>
  </div>
</template>
