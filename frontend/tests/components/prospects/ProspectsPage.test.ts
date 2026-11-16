import { flushPromises, mount } from '@vue/test-utils';
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query';
import PrimeVue from 'primevue/config';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, expect, it, vi } from 'vitest';
import { configureApiClient } from '../../../src/api/client';
import { useSession } from '../../../src/features/session/composables/useSession';
import ProspectsPage from '../../../src/features/prospects/pages/ProspectsPage.vue';
import { activity, prospect } from './prospectFixture';

const mounted: { unmount: () => void }[] = [];
const clients: QueryClient[] = [];

function stubBrowserAPIs(): void {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

async function render(path = '/prospects?prospect_id=prospect-1') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/prospects', component: ProspectsPage },
      { path: '/elsewhere', component: { template: '<h1>Elsewhere</h1>' } },
    ],
  });
  await router.push(path);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
  clients.push(client);
  const wrapper = mount(
    { template: '<RouterView />' },
    {
      global: { plugins: [router, PrimeVue, [VueQueryPlugin, { queryClient: client }]] },
    },
  );
  mounted.push(wrapper);
  await flushPromises();
  return { wrapper, router, client };
}

async function settle(): Promise<void> {
  await flushPromises();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await flushPromises();
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  for (const client of clients.splice(0)) client.clear();
  useSession().clear();
  configureApiClient({});
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.history.replaceState({}, '', '/');
});

it('retains a lost-response command outside filtered results and retries the exact captured intent', async () => {
  const serverProspect = prospect();
  let lostFirstResponse = true;
  const stageRequests: { url: string; body: string }[] = [];
  const listRequests: URL[] = [];
  stubBrowserAPIs();
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost');
    if (url.pathname === '/api/v1/sessions/current')
      return Response.json({
        account_id: 'account-1',
        user_id: 'user-1',
        csrf_token: 'session-proof',
        expires_at: '2099-01-01T00:00:00Z',
      });
    if (url.pathname === '/api/v1/prospects') {
      listRequests.push(url);
      const visible = !url.searchParams.get('search')?.includes('missing');
      return Response.json({
        items: visible ? [serverProspect] : [],
        offset: Number(url.searchParams.get('offset') ?? 0),
        limit: Number(url.searchParams.get('limit') ?? 25),
        has_more: url.searchParams.get('offset') !== '25',
      });
    }
    if (url.pathname === '/api/v1/prospects/prospect-1' && init?.method === 'GET')
      return Response.json(serverProspect);
    if (url.pathname === '/api/v1/prospects/prospect-1/stage') {
      const body = String(init?.body ?? '');
      stageRequests.push({ url: url.pathname, body });
      serverProspect.stage = 'proposal_sent';
      serverProspect.version = 5;
      serverProspect.updated_at = '2026-11-15T10:00:00Z';
      serverProspect.activities = [
        ...(serverProspect.activities ?? []),
        activity({
          id: `activity-${stageRequests.length}`,
          kind: 'stage_changed',
          occurred_at: '2026-11-15T10:00:00Z',
          effective_occurred_at: '2026-11-15T10:00:00Z',
          recorded_at: '2026-11-15T10:00:01Z',
          payload: { from_stage: 'in_conversation', to_stage: 'proposal_sent', reason: null },
        }),
      ];
      if (lostFirstResponse) {
        lostFirstResponse = false;
        throw new TypeError('The server committed, then the connection closed.');
      }
      return Response.json({
        prospect: {
          id: serverProspect.id,
          business_id: serverProspect.business_id,
          company_id: serverProspect.company_id,
          stage: serverProspect.stage,
          last_active_stage: null,
          notes: serverProspect.notes,
          follow_up_at: serverProspect.follow_up_at,
          created_at: serverProspect.created_at,
          updated_at: serverProspect.updated_at,
          version: serverProspect.version,
        },
        activity: activity({ kind: 'stage_changed' }),
      });
    }
    throw new Error(`Unexpected request ${init?.method ?? 'GET'} ${url.pathname}`);
  });
  vi.stubGlobal('fetch', fetcher);
  await useSession().bootstrap();
  const { wrapper } = await render();
  await vi.waitFor(() => expect(wrapper.text()).toContain('Current stage:'));
  expect(wrapper.text()).toContain('Northstar Research');
  expect(wrapper.text()).toContain('Why this prospect was saved');

  const forward = wrapper
    .findAll('button')
    .find((candidate) => candidate.text().includes('Move to proposal sent'));
  if (!forward) throw new Error('Forward stage action was not rendered');
  await forward.trigger('click');
  const form = wrapper.find('form');
  expect(form.exists()).toBe(true);
  await form.trigger('submit');
  await settle();

  expect(stageRequests).toHaveLength(1);
  const original = stageRequests[0];
  if (!original) throw new Error('Stage request was not captured');
  expect(JSON.parse(original.body)).toMatchObject({
    expected_version: 4,
    target_stage: 'proposal_sent',
    request_key: expect.any(String),
  });
  expect(wrapper.text()).toContain('The result is uncertain');
  expect(wrapper.text()).toContain('Drafts and commands to recover');

  const search = wrapper.get('input[aria-label="Search prospects by company name or domain"]');
  await search.setValue('missing.example');
  await settle();
  expect(listRequests.at(-1)?.searchParams.get('search')).toBe('missing.example');
  expect(wrapper.text()).toContain('No prospects match this view.');
  expect(wrapper.text()).toContain('Northstar Research');
  expect(stageRequests).toHaveLength(1);

  const retry = wrapper
    .findAll('button')
    .find((candidate) => candidate.text().includes('Retry the exact same request'));
  if (!retry) throw new Error('Exact retry action is not available');
  await retry.trigger('click');
  await settle();
  expect(stageRequests).toHaveLength(2);
  expect(stageRequests[1]).toEqual(original);
  expect(wrapper.text()).toContain('Current stage: proposal sent');
});

it('guards navigation and unload while prospect edits are unsaved', async () => {
  stubBrowserAPIs();
  vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost');
    if (url.pathname === '/api/v1/sessions/current')
      return Response.json({
        account_id: 'account-1',
        user_id: 'user-1',
        csrf_token: 'session-proof',
        expires_at: '2099-01-01T00:00:00Z',
      });
    if (url.pathname === '/api/v1/prospects')
      return Response.json({ items: [prospect()], offset: 0, limit: 25, has_more: false });
    if (url.pathname === '/api/v1/prospects/prospect-1') return Response.json(prospect());
    throw new Error(`Unexpected request ${url.pathname}`);
  });
  await useSession().bootstrap();
  const confirm = vi.fn(() => false);
  vi.stubGlobal('confirm', confirm);
  const { wrapper, router } = await render();
  await vi.waitFor(() => expect(wrapper.text()).toContain('Current stage:'));
  const backward = wrapper
    .findAll('button')
    .find((candidate) => candidate.text().includes('Move back to contacted'));
  if (!backward) throw new Error('Backward stage action was not rendered');
  await backward.trigger('click');

  const beforeUnload = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(beforeUnload);
  expect(beforeUnload.defaultPrevented).toBe(true);
  await router.push('/elsewhere');
  await settle();
  expect(confirm).toHaveBeenCalledOnce();
  expect(router.currentRoute.value.path).toBe('/prospects');
  expect(wrapper.text()).not.toContain('Elsewhere');
});

it('keeps an unsaved memo in the session recovery registry after an explicitly confirmed route leave', async () => {
  const requests: string[] = [];
  vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost');
    requests.push(`${url.pathname} ${url.search}`);
    if (url.pathname === '/api/v1/sessions/current')
      return Response.json({
        account_id: 'account-1',
        user_id: 'user-1',
        csrf_token: 'session-proof',
        expires_at: '2099-01-01T00:00:00Z',
      });
    if (url.pathname === '/api/v1/prospects')
      return Response.json({ items: [prospect()], offset: 0, limit: 25, has_more: false });
    if (url.pathname === '/api/v1/prospects/prospect-1') return Response.json(prospect());
    throw new Error(`Unexpected request ${url.pathname}`);
  });
  stubBrowserAPIs();
  await useSession().bootstrap();
  const confirm = vi.fn(() => true);
  vi.stubGlobal('confirm', confirm);
  const { wrapper, router } = await render();
  await vi.waitFor(() => expect(wrapper.text()).toContain('Current stage:'));
  const edit = wrapper
    .findAll('button')
    .find((candidate) => candidate.text().includes('Edit notes'));
  if (!edit) throw new Error('Edit notes action was not rendered');
  await edit.trigger('click');
  await wrapper.get('textarea').setValue('A draft retained across navigation.');
  await router.push('/elsewhere');
  await settle();
  expect(confirm).toHaveBeenCalledOnce();
  expect(router.currentRoute.value.path).toBe('/elsewhere');

  await router.push('/prospects?prospect_id=prospect-1');
  await settle();
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe(
    'A draft retained across navigation.',
  );
  expect(requests.filter((request) => request.includes('/notes'))).toEqual([]);
});
