import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { createRouter, createWebHistory, type Router } from 'vue-router';
import { useProofFragment } from '../../src/features/account-lifecycle/composables/useProofFragment';

const mounted: { unmount: () => void }[] = [];

function mountProofFragment(router?: Router) {
  let proof!: ReturnType<typeof useProofFragment>;
  // eslint-disable-next-line vue/one-component-per-file
  const component = defineComponent({
    setup() {
      proof = useProofFragment();
      return () =>
        h('div', [
          h('output', { 'data-testid': 'status' }, proof.status.value),
          h('output', { 'data-testid': 'token' }, proof.token.value ?? ''),
        ]);
    },
  });
  const wrapper = mount(component, router ? { global: { plugins: [router] } } : {});
  mounted.push(wrapper);
  return { wrapper, proof };
}

function setLocation(url: string, state: unknown = { router: 'history-state' }) {
  window.history.replaceState(state, '', url);
}

beforeEach(() => {
  window.history.replaceState({}, '', '/');
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
});

it('accepts a reopened native fragment in the mounted page and removes it without submitting', async () => {
  setLocation('/verify-email');
  const { proof } = mountProofFragment();
  setLocation('/verify-email#token=reopened-proof');
  window.dispatchEvent(new HashChangeEvent('hashchange'));
  await nextTick();

  expect(proof.token.value).toBe('reopened-proof');
  expect(proof.status.value).toBe('valid');
  expect(window.location.hash).toBe('');
  expect(fetch).not.toHaveBeenCalled();
});

it('rejects a malformed reopened fragment and clears the previous proof', () => {
  setLocation('/reset-password#token=previous-proof');
  const { proof } = mountProofFragment();
  setLocation('/reset-password#token=first&token=second');
  window.dispatchEvent(new HashChangeEvent('hashchange'));

  expect(proof.token.value).toBeNull();
  expect(proof.status.value).toBe('invalid');
  expect(window.location.hash).toBe('');
  expect(fetch).not.toHaveBeenCalled();
});

it('accepts a reopened Vue Router fragment and scrubs route/history without submitting', async () => {
  const router = createRouter({
    history: createWebHistory(),
    // eslint-disable-next-line vue/one-component-per-file
    routes: [{ path: '/reset-password', component: defineComponent({ render: () => h('div') }) }],
  });
  await router.push('/reset-password');
  const { proof } = mountProofFragment(router);
  await router.push('/reset-password#token=reopened-router-proof');
  await flushPromises();

  expect(proof.token.value).toBe('reopened-router-proof');
  expect(window.location.hash).toBe('');
  expect(router.currentRoute.value.hash).toBe('');
  expect(JSON.stringify(window.history.state)).not.toContain('reopened-router-proof');
  expect(JSON.stringify(router.options.history.state)).not.toContain('reopened-router-proof');
  expect(fetch).not.toHaveBeenCalled();
});

it('loads only a valid fragment token into component memory and immediately scrubs history', () => {
  const routerState = {
    back: '/check-email',
    current: '/verify-email?source=mail',
    forward: null,
    position: 8,
    replaced: false,
    scroll: null,
  };
  setLocation('/verify-email?source=mail#token=opaque-proof_123', routerState);
  const { wrapper, proof } = mountProofFragment();

  expect(proof.status.value).toBe('valid');
  expect(proof.token.value).toBe('opaque-proof_123');
  expect(wrapper.get('[data-testid="status"]').text()).toBe('valid');
  expect(wrapper.get('[data-testid="token"]').text()).toBe('opaque-proof_123');
  expect(window.location.pathname).toBe('/verify-email');
  expect(window.location.search).toBe('?source=mail');
  expect(window.location.hash).toBe('');
  expect(window.history.state).toEqual(routerState);
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
  expect(fetch).not.toHaveBeenCalled();
});

it.each([
  { name: 'empty token', fragment: '#token=' },
  { name: 'duplicate token', fragment: '#token=first&token=second' },
  { name: 'unexpected parameter', fragment: '#token=valid-proof&other=value' },
  { name: 'unexpected parameter alone', fragment: '#other=value' },
  { name: 'spaces', fragment: '#token=has%20space' },
  { name: 'encoded line breaks', fragment: '#token=first%0D%0ABcc%3Aevil' },
  { name: 'oversized token', fragment: `#token=${'a'.repeat(1025)}` },
  { name: 'non URL-safe token', fragment: '#token=contains%2Fslash' },
])('rejects $name and still removes the entire fragment', ({ fragment }) => {
  setLocation(`/reset-password?source=mail${fragment}`);
  const { wrapper, proof } = mountProofFragment();

  expect(proof.status.value).toBe('invalid');
  expect(proof.token.value).toBeNull();
  expect(wrapper.get('[data-testid="token"]').text()).toBe('');
  expect(window.location.pathname).toBe('/reset-password');
  expect(window.location.search).toBe('?source=mail');
  expect(window.location.hash).toBe('');
  expect(fetch).not.toHaveBeenCalled();
});

it('does not accept a token from the query string', () => {
  setLocation('/reset-password?token=query-proof&source=mail');
  const { proof } = mountProofFragment();

  expect(proof.status.value).toBe('missing');
  expect(proof.token.value).toBeNull();
  expect(window.location.search).toBe('?token=query-proof&source=mail');
});

it('reports a missing token after history has been scrubbed and the page reloads', () => {
  setLocation('/verify-email#token=one-time-proof');
  const first = mountProofFragment();
  expect(first.proof.token.value).toBe('one-time-proof');
  first.wrapper.unmount();

  const second = mountProofFragment();

  expect(second.proof.status.value).toBe('missing');
  expect(second.proof.token.value).toBeNull();
  expect(window.location.hash).toBe('');
});

it('clears the proof explicitly after consumption and on component unmount', () => {
  setLocation('/verify-email#token=one-time-proof');
  const first = mountProofFragment();
  first.proof.clearProof();
  expect(first.proof.token.value).toBeNull();
  expect(first.proof.status.value).toBe('cleared');
  first.wrapper.unmount();

  setLocation('/reset-password#token=another-proof');
  const second = mountProofFragment();
  expect(second.proof.token.value).toBe('another-proof');
  second.wrapper.unmount();
  expect(second.proof.token.value).toBeNull();
  expect(second.proof.status.value).toBe('cleared');
});

it('does not log the proof or persist it in browser storage', () => {
  setLocation('/verify-email#token=secret-proof');
  const log = vi.spyOn(console, 'log');
  const warn = vi.spyOn(console, 'warn');
  const error = vi.spyOn(console, 'error');
  const { proof } = mountProofFragment();

  expect(proof.token.value).toBe('secret-proof');
  expect(log).not.toHaveBeenCalled();
  expect(warn).not.toHaveBeenCalled();
  expect(error).not.toHaveBeenCalled();
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
});

it('removes proof fragments from Vue Router history state and active route', async () => {
  const secret = 'router-history-secret';
  // eslint-disable-next-line vue/one-component-per-file
  const viewComponent = defineComponent({ setup: () => () => h('div') });
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/before', component: viewComponent },
      { path: '/verify-email', component: viewComponent },
      { path: '/after', component: viewComponent },
    ],
  });
  await router.push(`/before#token=${secret}`);
  await router.push(`/verify-email#token=${secret}`);
  window.history.replaceState(
    {
      ...window.history.state,
      forward: `/after#token=${secret}`,
      routerMarker: 'keep-this-metadata',
    },
    '',
    window.location.href,
  );

  expect(JSON.stringify(window.history.state)).toContain(secret);
  const { wrapper, proof } = mountProofFragment(router);
  await flushPromises();
  await nextTick();

  expect(proof.token.value).toBe(secret);
  expect(window.location.hash).toBe('');
  expect(JSON.stringify(window.history.state)).not.toContain(secret);
  expect(JSON.stringify(router.options.history.state)).not.toContain(secret);
  expect(window.history.state.routerMarker).toBe('keep-this-metadata');
  expect(window.history.state.back).toBe('/before');
  expect(window.history.state.current).toBe('/verify-email');
  expect(window.history.state.forward).toBe('/after');
  expect(router.currentRoute.value.hash).toBe('');
  expect(router.currentRoute.value.fullPath).toBe('/verify-email');
  expect(router.options.history.location).toBe('/verify-email');

  await router.push('/after');
  await flushPromises();
  expect(JSON.stringify(window.history.state)).not.toContain(secret);
  router.back();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await flushPromises();
  await nextTick();
  expect(window.location.hash).toBe('');
  expect(router.currentRoute.value.hash).toBe('');
  expect(JSON.stringify(window.history.state)).not.toContain(secret);

  wrapper.unmount();
  expect(proof.token.value).toBeNull();
});
