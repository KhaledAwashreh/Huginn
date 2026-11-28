<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Password from 'primevue/password';
import { ApiError } from '../../../api/apiError';
import FieldFeedback from '../../../shared/ui/FieldFeedback.vue';
import { validateReturnPath } from '../../../shared/navigation/validateReturnPath';
import { useSession } from '../composables/useSession';

const router = useRouter();
const route = useRoute();
const session = useSession();
const emailMode = computed(() => route.query.method !== 'username');
const identifierId = computed(() => (emailMode.value ? 'login-email' : 'login-username'));
const draft = reactive({ identifier: '', password: '' });
const pending = ref(false);
const message = ref('');
watch(emailMode, () => {
  draft.identifier = '';
  draft.password = '';
  message.value = '';
});
async function submit(): Promise<void> {
  if (pending.value) return;
  pending.value = true;
  message.value = '';
  try {
    const identifier = draft.identifier.trim();
    await session.login({
      ...(emailMode.value ? { email: identifier } : { username: identifier }),
      password: draft.password,
    });
    await router.replace(validateReturnPath(route.query.return));
  } catch (error) {
    message.value =
      error instanceof ApiError
        ? error.status === 401
          ? `Unable to sign in. Check your ${emailMode.value ? 'email' : 'username'} and password. If you just created an account, verify your email first.`
          : error.message
        : 'Sign in could not be completed. Check your connection and try again.';
  } finally {
    draft.password = '';
    pending.value = false;
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card" aria-labelledby="login-title">
      <p class="brand">Huginn</p>
      <h1 id="login-title" tabindex="-1">Welcome back</h1>
      <p class="muted">Sign in to your workspace.</p>
      <form class="form-stack" @submit.prevent="submit">
        <div class="field-group">
          <label :for="identifierId">{{ emailMode ? 'Email' : 'Username' }}</label>
          <InputText
            :id="identifierId"
            v-model="draft.identifier"
            :type="emailMode ? 'email' : 'text'"
            autocomplete="username"
            required
            :disabled="pending"
          />
        </div>
        <div class="field-group">
          <label for="login-password">Password</label>
          <Password
            v-model="draft.password"
            input-id="login-password"
            :feedback="false"
            :disabled="pending"
            :input-props="{
              autocomplete: 'current-password',
              'aria-expanded': undefined,
              'aria-haspopup': undefined,
              required: true,
              'aria-describedby': message ? 'login-error' : undefined,
            }"
          />
        </div>
        <FieldFeedback id="login-error" :message="message" />
        <Button type="submit" label="Sign in" :loading="pending" :disabled="pending" />
      </form>
      <p>
        <RouterLink
          :to="{
            path: '/login',
            query: { ...route.query, method: emailMode ? 'username' : undefined },
          }"
        >
          {{ emailMode ? 'Sign in with username' : 'Sign in with email' }}
        </RouterLink>
      </p>
      <p><RouterLink to="/create-account">Create account</RouterLink></p>
      <p><RouterLink to="/forgot-password">Forgot password</RouterLink></p>
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
  width: min(100%, 400px);
  padding: var(--space-8);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}
.brand {
  margin: 0 0 var(--space-6);
  color: var(--color-primary);
  font-weight: 700;
  letter-spacing: -0.02em;
}
h1 {
  font-size: 24px;
  line-height: 1.25;
  margin: 0;
}
.muted {
  color: var(--color-text-muted);
  margin: var(--space-2) 0 var(--space-6);
}
.form-stack,
.field-group {
  display: grid;
  gap: var(--space-2);
}
.form-stack {
  gap: var(--space-5);
}
.field-group label {
  font-weight: 600;
}
:deep(.p-password),
:deep(.p-password-input) {
  width: 100%;
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
