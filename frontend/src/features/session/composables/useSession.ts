import { computed, readonly, ref } from 'vue';
import { configureApiClient } from '../../../api/client';
import { ApiError } from '../../../api/apiError';
import { queryClient } from '../../../app/queryClient';
import { getCurrentSession } from '../api/getCurrentSession';
import { login as submitLogin } from '../api/login';
import { logout as submitLogout } from '../api/logout';
import type { SessionContext } from '../sessionContext';
import type { LoginDraft } from '../forms/loginDraft';

const context = ref<SessionContext | null>(null);
const restored = ref(false);
let bootstrapInFlight: Promise<void> | null = null;
let generation = 0;
let bootstrapController: AbortController | null = null;

function clear(): void {
  generation++;
  bootstrapController?.abort();
  bootstrapController = null;
  bootstrapInFlight = null;
  context.value = null;
  restored.value = true;
  void queryClient.cancelQueries();
  queryClient.clear();
}

function demoteAdministrator(): void {
  if (context.value?.role !== 'admin') return;
  generation++;
  context.value = { ...context.value, role: 'user' };
  const adminQueries = {
    predicate: (query: { queryKey: readonly unknown[] }) => query.queryKey[0] === 'admin',
  };
  void queryClient.cancelQueries(adminQueries);
  queryClient.removeQueries(adminQueries);
}

async function bootstrap(): Promise<void> {
  if (bootstrapInFlight) return bootstrapInFlight;
  const startedGeneration = generation;
  const controller = new AbortController();
  bootstrapController = controller;
  const flight = (async () => {
    try {
      const next = await getCurrentSession(controller.signal);
      if (generation !== startedGeneration) return;
      if (
        context.value?.account_id !== next.account_id ||
        context.value?.user_id !== next.user_id ||
        context.value?.csrf_token !== next.csrf_token
      ) {
        generation++;
        void queryClient.cancelQueries();
        queryClient.clear();
      }
      if (context.value?.role === 'admin' && next.role !== 'admin') demoteAdministrator();
      context.value = next;
      restored.value = true;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        if (generation === startedGeneration) clear();
        return;
      }
      throw error;
    }
  })();
  bootstrapInFlight = flight;
  try {
    await flight;
  } finally {
    if (bootstrapInFlight === flight) {
      bootstrapInFlight = null;
      bootstrapController = null;
    }
  }
}

async function login(draft: LoginDraft): Promise<void> {
  clear();
  await submitLogin(draft);
  await bootstrap();
  if (!context.value) throw new Error('Sign in could not be restored. Try again.');
}

async function logout(): Promise<void> {
  try {
    await submitLogout();
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) throw error;
  }
  clear();
}

export function useSession() {
  configureApiClient({
    getCsrfToken: () => context.value?.csrf_token,
    onUnauthorized: clear,
    onAdministratorForbidden: demoteAdministrator,
    getIdentityVersion: () => generation,
  });
  return {
    context: readonly(context),
    restored: readonly(restored),
    isAuthenticated: computed(() => context.value !== null),
    isAdministrator: computed(() => context.value?.role === 'admin'),
    demoteAdministrator,
    bootstrap,
    login,
    logout,
    clear,
  };
}
