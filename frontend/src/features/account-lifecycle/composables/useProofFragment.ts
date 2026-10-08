import { inject, onBeforeUnmount, readonly, ref, watch, type Ref } from 'vue';
import { routerKey, type HistoryState, type Router } from 'vue-router';

export type ProofFragmentStatus = 'valid' | 'missing' | 'invalid' | 'cleared';

const PROOF_PATTERN = /^[A-Za-z0-9_-]{1,1024}$/;
const ROUTER_HISTORY_FIELDS = ['back', 'current', 'forward'] as const;

export function useProofFragment(): {
  token: Readonly<Ref<string | null>>;
  status: Readonly<Ref<ProofFragmentStatus>>;
  clearProof: () => void;
} {
  const token = ref<string | null>(null);
  const status = ref<ProofFragmentStatus>('missing');
  const router = inject<Router | null>(routerKey, null);

  function readFragment(fragment: string): void {
    if (fragment) {
      token.value = null;
      const parameters = new URLSearchParams(fragment.slice(1));
      const keys = [...parameters.keys()];
      const values = parameters.getAll('token');
      const candidate = values[0];

      if (
        keys.length === 1 &&
        keys[0] === 'token' &&
        values.length === 1 &&
        candidate !== undefined &&
        PROOF_PATTERN.test(candidate)
      ) {
        token.value = candidate;
        status.value = 'valid';
      } else {
        status.value = 'invalid';
      }

      cleanHistory(fragment, router);
    }
  }

  function readBrowserFragment(): void {
    readFragment(window.location.hash);
  }

  if (typeof window !== 'undefined') {
    readBrowserFragment();
    window.addEventListener('hashchange', readBrowserFragment);
    if (router) watch(() => router.currentRoute.value.hash, readFragment);
  }

  function clearProof(): void {
    token.value = null;
    status.value = 'cleared';
  }

  onBeforeUnmount(() => {
    if (typeof window !== 'undefined')
      window.removeEventListener('hashchange', readBrowserFragment);
    clearProof();
  });

  return {
    token: readonly(token),
    status: readonly(status),
    clearProof,
  };
}

function cleanHistory(fragment: string, router: Router | null): void {
  if (router) {
    const browserState = asRecord(window.history.state);
    const routerState = asRecord(router.options.history.state);
    const state = sanitizeRouterState(
      { ...routerState, ...browserState },
      fragment,
    ) as HistoryState;
    const historyLocation = stripProofFragment(router.options.history.location, fragment);
    router.options.history.replace(historyLocation, state);

    const currentRoute = router.currentRoute.value;
    if (containsProofFragment(currentRoute.fullPath, fragment)) {
      void router
        .replace({ path: currentRoute.path, query: currentRoute.query, hash: '' })
        .catch(() => {
          const active = router.currentRoute.value;
          if (containsProofFragment(active.fullPath, fragment)) {
            router.currentRoute.value = {
              ...active,
              fullPath: stripProofFragment(active.fullPath, fragment),
              hash: '',
            };
          }
        });
      return;
    }
  }

  const state = sanitizeRouterState(asRecord(window.history.state), fragment);
  window.history.replaceState(state, '', `${window.location.pathname}${window.location.search}`);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? { ...value } : {};
}

function sanitizeRouterState(
  state: Record<string, unknown>,
  fragment: string,
): Record<string, unknown> {
  const sanitized = { ...state };
  for (const key of ROUTER_HISTORY_FIELDS) {
    const location = sanitized[key];
    if (typeof location === 'string') {
      sanitized[key] = stripProofFragment(location, fragment);
    }
  }
  return sanitized;
}

function stripProofFragment(location: string, currentFragment: string): string {
  const separator = location.indexOf('#');
  if (separator < 0) return location;
  const fragment = location.slice(separator);
  if (fragment === currentFragment || containsProofFragment(location, currentFragment)) {
    return location.slice(0, separator);
  }
  return location;
}

function containsProofFragment(location: string, currentFragment: string): boolean {
  const separator = location.indexOf('#');
  if (separator < 0) return false;
  const fragment = location.slice(separator);
  return fragment === currentFragment || new URLSearchParams(fragment.slice(1)).has('token');
}
