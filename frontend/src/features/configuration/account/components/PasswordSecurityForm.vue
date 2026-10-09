<script setup lang="ts">
import { onBeforeUnmount, reactive, ref } from 'vue';
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRouter } from 'vue-router';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import { ApiError } from '../../../../api/apiError';
import FieldFeedback from '../../../../shared/ui/FieldFeedback.vue';
import { useSession } from '../../../session/composables/useSession';
import { changePassword } from '../api/changePassword';
import { createPasswordChangeDraft } from '../forms/passwordChangeDraft';
const router = useRouter();
const session = useSession();
const draft = reactive(createPasswordChangeDraft());
const pending = ref(false);
const message = ref('');
const uncertain = ref(false);
async function signInAgain(): Promise<void> {
  clear();
  pending.value = false;
  session.clear();
  await router.replace({ name: 'login' });
}
function clear(): void {
  draft.current_password = '';
  draft.new_password = '';
}
onBeforeUnmount(clear);
function canLeave(): boolean {
  if (pending.value) return false;
  if (!draft.current_password && !draft.new_password) return true;
  return typeof window === 'undefined' || window.confirm('Discard the unsaved password change?');
}
onBeforeRouteLeave(canLeave);
onBeforeRouteUpdate(canLeave);
async function submit(): Promise<void> {
  if (pending.value || uncertain.value) return;
  pending.value = true;
  message.value = '';
  try {
    await changePassword({
      current_password: draft.current_password,
      new_password: draft.new_password,
    });
    clear();
    pending.value = false;
    session.clear();
    await router.replace({ name: 'login' });
  } catch (error) {
    if (!(error instanceof ApiError) || error.status >= 500) {
      uncertain.value = true;
      clear();
      message.value =
        'The password change outcome is unknown. Sign in again with your new password. If it was not accepted, try your previous password. Do not submit the change again until you have checked.';
      return;
    }
    if (error instanceof ApiError && error.status === 401) clear();
    message.value =
      error instanceof ApiError && error.status === 401
        ? 'Sign in again and check your current password.'
        : error instanceof ApiError && (error.status === 403 || error.status === 429)
          ? error.message
          : 'Password could not be changed. Check your current password and try again.';
  } finally {
    pending.value = false;
  }
}
</script>
<template>
  <section class="security" aria-labelledby="password-title">
    <h2 id="password-title">Password</h2>
    <p>Changing your password signs out all active sessions.</p>
    <form class="fields" @submit.prevent="submit">
      <label for="current-password">Current password</label>
      <InputText
        id="current-password"
        v-model="draft.current_password"
        type="password"
        autocomplete="current-password"
        required
        :disabled="pending"
      />
      <label for="new-password">New password</label>
      <InputText
        id="new-password"
        v-model="draft.new_password"
        type="password"
        autocomplete="new-password"
        required
        :disabled="pending"
      />
      <FieldFeedback :message="message" />
      <Button
        v-if="uncertain || !session.isAuthenticated.value"
        type="button"
        label="Sign in again"
        severity="secondary"
        @click="signInAgain"
      />
      <div class="actions">
        <Button
          type="button"
          label="Cancel"
          severity="secondary"
          :disabled="pending"
          @click="clear"
        />
        <Button
          type="submit"
          label="Change password"
          :loading="pending"
          :disabled="pending || uncertain || !draft.current_password || !draft.new_password"
        />
      </div>
    </form>
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
.fields {
  display: grid;
  gap: var(--space-3);
  max-width: 32rem;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
h2 {
  margin-top: 0;
}
</style>
