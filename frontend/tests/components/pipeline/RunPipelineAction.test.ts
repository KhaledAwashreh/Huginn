import { flushPromises, mount } from '@vue/test-utils';
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query';
import { createMemoryHistory, createRouter } from 'vue-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/api/apiError';
import RunPipelineAction from '@/features/pipeline/components/RunPipelineAction.vue';
import type { components } from '@/api/generated/schema';

const triggerInvocationMock = vi.hoisted(() => vi.fn());
vi.mock('@/features/pipeline/api/triggerInvocation', () => ({
  triggerInvocation: triggerInvocationMock,
}));

type Receipt = components['schemas']['InvocationReceiptResponse'];
const invocationId = '6ec48cf0-1632-4f3d-9ed3-68dc71af4429';
const requestId = '7ec48cf0-1632-4f3d-9ed3-68dc71af4429';

async function mountAction() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin/pipeline', component: { template: '<div>History</div>' } },
      {
        path: '/admin/pipeline/invocations/:id',
        component: { template: '<div>Invocation</div>' },
      },
    ],
  });
  await router.push('/admin/pipeline');
  await router.isReady();
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const wrapper = mount(RunPipelineAction, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient }]] },
  });
  return { wrapper, router, queryClient };
}

describe('Pull data outcome handling', () => {
  beforeEach(() => {
    triggerInvocationMock.mockReset();
    vi.spyOn(window.crypto, 'randomUUID').mockReturnValue(requestId);
  });

  it('navigates to the queued invocation from an accepted trigger receipt', async () => {
    const accepted: Receipt = {
      id: invocationId,
      requested_at: '2026-10-09T09:00:00Z',
      status: 'queued',
    };
    let resolveReceipt: (receipt: Receipt) => void = () => {};
    triggerInvocationMock.mockReturnValueOnce(
      new Promise<Receipt>((resolve) => {
        resolveReceipt = resolve;
      }),
    );
    const { wrapper, router } = await mountAction();

    await wrapper.get('button').trigger('click');
    await wrapper.get('button').trigger('click');
    expect(triggerInvocationMock).toHaveBeenCalledTimes(1);
    resolveReceipt(accepted);
    await flushPromises();

    expect(triggerInvocationMock).toHaveBeenCalledWith(requestId);
    expect(router.currentRoute.value.fullPath).toBe(`/admin/pipeline/invocations/${invocationId}`);
  });

  it('opens a 202 receipt and retries an uncertain response with the same request ID', async () => {
    const accepted: Receipt = {
      id: invocationId,
      requested_at: '2026-10-09T09:00:00Z',
      status: 'queued',
    };
    triggerInvocationMock.mockRejectedValueOnce(new Error('Network response lost'));
    triggerInvocationMock.mockResolvedValueOnce(accepted);
    const { wrapper, router } = await mountAction();

    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('outcome is unknown');
    expect(wrapper.get('button').attributes('disabled')).toBeDefined();
    expect(triggerInvocationMock).toHaveBeenCalledTimes(1);
    expect(triggerInvocationMock).toHaveBeenNthCalledWith(1, requestId);

    const retryButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Retry same request'));
    if (!retryButton) throw new Error('The explicit same-request retry action is missing.');
    await retryButton.trigger('click');
    await flushPromises();
    expect(triggerInvocationMock).toHaveBeenCalledTimes(2);
    expect(triggerInvocationMock).toHaveBeenNthCalledWith(2, requestId);
    expect(router.currentRoute.value.fullPath).toBe(`/admin/pipeline/invocations/${invocationId}`);
  });

  it('links to the active invocation on a safe 409 and does not retry it', async () => {
    triggerInvocationMock.mockRejectedValue(
      new ApiError(
        409,
        'active_invocation_conflict',
        'An invocation is active',
        [],
        [{ active_invocation_id: invocationId }],
      ),
    );
    const { wrapper } = await mountAction();

    await wrapper.get('button').trigger('click');
    await flushPromises();

    expect(wrapper.get('a[href="/admin/pipeline/invocations/' + invocationId + '"]').text()).toBe(
      'Open active invocation',
    );
    expect(triggerInvocationMock).toHaveBeenCalledTimes(1);
    expect(wrapper.get('button').attributes('disabled')).toBeDefined();
  });
});
