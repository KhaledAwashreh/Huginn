import { flushPromises, mount } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { computed, defineComponent, ref } from 'vue';
import { expect, it, vi } from 'vitest';
import {
  createRecommendationCommandDraft,
  resetRecommendationDecisionDraft,
} from '../../../src/features/recommendations/models/recommendationCommandDraft';
import type { RecommendationView } from '../../../src/features/recommendations/models/prospecting';
import { useRecommendationCommands } from '../../../src/features/recommendations/composables/useRecommendationCommands';

function setup() {
  const identity = ref('account-1:user-1:csrf-1');
  let commands!: ReturnType<typeof useRecommendationCommands>;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = mount(
    defineComponent({
      setup() {
        commands = useRecommendationCommands(computed(() => identity.value));
        return () => null;
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { commands, identity, queryClient, wrapper };
}

it('discards a command result and error state when the authenticated identity changes in flight', async () => {
  const { commands, identity, queryClient, wrapper } = setup();
  const invalidation = vi.spyOn(queryClient, 'invalidateQueries');
  let resolveAction!: (value: { saved: boolean }) => void;
  const action = new Promise<{ saved: boolean }>((resolve) => {
    resolveAction = resolve;
  });

  const pending = commands.execute(() => action);
  expect(commands.pending.value).toBe(true);
  identity.value = 'account-2:user-2:csrf-2';
  await flushPromises();
  resolveAction({ saved: true });

  await expect(pending).resolves.toBeUndefined();
  expect(commands.pending.value).toBe(false);
  expect(commands.error.value).toBe('');
  expect(commands.canRetry.value).toBe(false);
  expect(commands.needsRefresh.value).toBe(false);
  expect(invalidation).not.toHaveBeenCalled();
  wrapper.unmount();
});

it('does not expose an uncertain retry from a previous identity', async () => {
  const { commands, identity, wrapper } = setup();
  let rejectAction!: (reason: Error) => void;
  const action = new Promise<never>((_resolve, reject) => {
    rejectAction = reject;
  });
  const pending = commands.execute(() => action);
  identity.value = 'account-2:user-2:csrf-2';
  await flushPromises();
  rejectAction(new TypeError('network interrupted'));

  await expect(pending).resolves.toBeUndefined();
  expect(commands.error.value).toBe('');
  expect(commands.canRetry.value).toBe(false);
  wrapper.unmount();
});

it('publishes a committed receipt before refetch can remove its row from the current page', async () => {
  const { commands, queryClient, wrapper } = setup();
  let finishInvalidation!: () => void;
  const invalidation = new Promise<void>((resolve) => {
    finishInvalidation = resolve;
  });
  vi.spyOn(queryClient, 'invalidateQueries').mockReturnValue(invalidation);
  const onSuccess = vi.fn();
  const pending = commands.execute(() => Promise.resolve({ saved: true }), onSuccess);
  await flushPromises();

  expect(onSuccess).toHaveBeenCalledWith({ saved: true });
  expect(commands.pending.value).toBe(true);
  finishInvalidation();
  await expect(pending).resolves.toEqual({ saved: true });
  wrapper.unmount();
});

it('clears a completed decision without pinning an unsent report or clearing its form', () => {
  const draft = createRecommendationCommandDraft('recommendation-1');
  const snapshot = { id: 'recommendation-1' } as RecommendationView;
  draft.snapshot = snapshot;
  draft.status = 'stale';
  draft.reason = 'A reason';
  draft.pauseChoice = 'x3';
  draft.laterConfirmationOpen = true;
  draft.feedback.open = true;
  draft.feedback.notes = 'Keep these separate notes';
  const feedback = draft.feedback;

  resetRecommendationDecisionDraft(draft);

  expect(draft).toEqual({
    ...createRecommendationCommandDraft('recommendation-1'),
    snapshot: null,
    feedback,
  });
  expect(draft.feedback).toBe(feedback);
  expect(draft.feedback.notes).toBe('Keep these separate notes');
  draft.feedback.open = false;
  draft.feedback.notes = '';

  resetRecommendationDecisionDraft(draft);

  expect(draft.snapshot).toBeNull();
});
