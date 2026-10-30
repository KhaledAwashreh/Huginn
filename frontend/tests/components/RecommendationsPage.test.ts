import { mount, flushPromises } from '@vue/test-utils';
import { ref, defineComponent, type PropType } from 'vue';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { beforeEach, expect, it, vi } from 'vitest';
import RecommendationsPage from '../../src/features/recommendations/pages/RecommendationsPage.vue';

const mocks = vi.hoisted(() => ({
  workspace: {} as Record<string, unknown>,
  replace: vi.fn(),
  leave: vi.fn(),
  weekly: true,
}));
vi.mock('../../src/features/recommendations/composables/useRecommendations', () => ({
  useRecommendations: () => mocks.workspace,
}));
vi.mock('vue-router', () => ({
  useRoute: () => ({
    path: mocks.weekly ? '/weekly-matches' : '/recommendations',
    query: { batch: 'saved-week' },
  }),
  useRouter: () => ({ replace: mocks.replace }),
  onBeforeRouteLeave: mocks.leave,
  onBeforeRouteUpdate: vi.fn(),
  RouterLink: { template: '<a><slot /></a>' },
}));
const listStub = defineComponent({
  props: { batch: { type: Object as PropType<{ id: string }>, required: true } },
  emits: ['saved', 'dirty'],
  template: '<div>Saved weekly selection: {{ batch.id }}</div>',
});
function query(data: unknown, error = false) {
  return {
    data: ref(data),
    isPending: ref(false),
    isError: ref(error),
    isFetching: ref(false),
    isSuccess: ref(!error),
    refetch: vi.fn(),
  };
}
function setup(weekly = true) {
  mocks.weekly = weekly;
  const client = new QueryClient();
  const batch = {
    id: 'saved-week',
    strategy_id: 'strategy',
    created_at: '2026-10-28T00:00:00Z',
    candidate_count: 1,
    items: [{}],
  };
  mocks.workspace = {
    identity: ref('identity'),
    pinnedBatch: ref('saved-week'),
    historyOffset: ref(0),
    weeklyHistory: query(undefined, true),
    strategies: query([]),
    batch: query(batch),
    feedback: query([]),
    feedbackKey: ref(['feedback', 'saved-week']),
    generating: ref(false),
    generationError: ref(''),
    strategyId: ref('strategy'),
    generate: vi.fn().mockResolvedValue(false),
  };
  const wrapper = mount(RecommendationsPage, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient: client }]],
      stubs: {
        RecommendationList: listStub,
        Select: true,
        Button: {
          props: { label: { type: String, required: true } },
          emits: ['click'],
          template: '<button @click="$emit(\'click\')">{{ label }}</button>',
        },
      },
    },
  });
  return { wrapper, client };
}
beforeEach(() => vi.clearAllMocks());
it('shows a pinned weekly selection when weekly history fails', () => {
  const { wrapper } = setup();
  expect(wrapper.text()).toContain('Weekly history could not be loaded');
  expect(wrapper.text()).toContain('Saved weekly selection: saved-week');
});
it('deduplicates a receipt already returned by a feedback GET', async () => {
  const { wrapper, client } = setup();
  const entry = { id: 'feedback-one', batch_id: 'saved-week' };
  client.setQueryData(['feedback', 'saved-week'], [entry]);
  wrapper.findComponent(listStub).vm.$emit('saved', entry);
  await flushPromises();
  expect(client.getQueryData(['feedback', 'saved-week'])).toEqual([entry]);
});
it('refreshes incomplete feedback rather than treating a receipt as full history', async () => {
  const { wrapper, client } = setup();
  const feedback = mocks.workspace.feedback as ReturnType<typeof query>;
  feedback.isSuccess.value = false;
  const refresh = vi.spyOn(client, 'invalidateQueries');
  wrapper.findComponent(listStub).vm.$emit('saved', { id: 'new', batch_id: 'saved-week' });
  await flushPromises();
  expect(refresh).toHaveBeenCalled();
  expect(client.getQueryData(['feedback', 'saved-week'])).toBeUndefined();
});

it('retains the feedback leave guard and saved URL after generation fails', async () => {
  const { wrapper } = setup(false);
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  wrapper.findComponent(listStub).vm.$emit('dirty', 'item-one', true);
  const generate = wrapper
    .findAll('button')
    .find((button) => button.text() === 'Generate recommendations');
  if (!generate) throw new Error('Generate button missing');
  await generate.trigger('click');
  await flushPromises();
  expect(mocks.workspace.generate).toHaveBeenCalledOnce();
  expect(mocks.replace).not.toHaveBeenCalled();
  confirm.mockReturnValue(false);
  const guard = mocks.leave.mock.calls[0];
  if (!guard) throw new Error('Leave guard missing');
  const leaveGuard = guard[0] as () => boolean;
  expect(leaveGuard()).toBe(false);
  confirm.mockRestore();
});
