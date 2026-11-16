import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, expect, it, vi } from 'vitest';
import { h } from 'vue';
import RecommendationPresentation from '../../../src/features/recommendations/components/RecommendationPresentation.vue';
import type { RecommendationView } from '../../../src/features/recommendations/models/prospecting';

const mocks = vi.hoisted(() => ({ prepare: vi.fn(), confirm: vi.fn(), visible: null as unknown }));
vi.mock('../../../src/features/recommendations/api/prepareRecommendationOffer', () => ({
  prepareRecommendationOffer: mocks.prepare,
}));
vi.mock('../../../src/features/recommendations/api/confirmRecommendationOffer', () => ({
  confirmRecommendationOffer: mocks.confirm,
}));

function item(
  first: string | null = null,
  assessmentPresented: string | null = first,
): RecommendationView {
  return {
    id: 'rec-1',
    current_revision_id: 'revision-1',
    first_presented_at: first,
    assessment_presented_at: assessmentPresented,
    status: 'open',
    assessment: { id: 'revision-1' },
    evidence_state: 'current',
    selection_blockers: [],
    company: { name: 'Visible Company' },
  } as unknown as RecommendationView;
}
beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(callback: unknown) {
        mocks.visible = callback;
      }
      observe() {}
      disconnect() {}
    },
  );
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width: 200,
    height: 100,
    top: 0,
    bottom: 100,
    left: 0,
    right: 200,
    x: 0,
    y: 0,
    toJSON() {},
  });
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  mocks.prepare.mockResolvedValue({
    offer_cycle_id: 'cycle-1',
    recommendation_id: 'rec-1',
    assessment_revision_id: 'revision-1',
    status: 'preparing',
    claim_token: 'secret-token',
    lease_expires_at: '2026-12-01T00:00:00Z',
    presented_at: null,
  });
  mocks.confirm.mockResolvedValue({ presented_at: '2026-11-15T00:00:00Z' });
});
function render(first: string | null = null, assessmentPresented: string | null = first) {
  return mount(RecommendationPresentation, {
    attachTo: document.body,
    props: { recommendation: item(first, assessmentPresented), identity: crypto.randomUUID() },
    slots: {
      default: ({ recommendation }: { recommendation: RecommendationView }) =>
        h(
          'p',
          { 'data-assessment-revision-id': 'revision-1' },
          `Exact assessment content ${recommendation.company.name}`,
        ),
    },
  });
}
async function visible() {
  (mocks.visible as (entries: { isIntersecting: boolean }[]) => void)([{ isIntersecting: true }]);
  await flushPromises();
}
it('prepares only when visible and confirms after the exact assessment has rendered', async () => {
  const wrapper = render();
  expect(mocks.prepare).not.toHaveBeenCalled();
  expect(wrapper.text()).not.toContain('Exact assessment content');
  mocks.confirm.mockImplementation(async () => {
    expect(wrapper.text()).toContain('Exact assessment content');
    return { presented_at: '2026-11-15T00:00:00Z' };
  });
  await visible();
  expect(mocks.confirm).not.toHaveBeenCalled();
  await visible();
  expect(mocks.prepare).toHaveBeenCalledWith(
    'rec-1',
    expect.objectContaining({ assessment_revision_id: 'revision-1' }),
  );
  expect(mocks.confirm).toHaveBeenCalledWith('cycle-1', { claim_token: 'secret-token' });
  expect(wrapper.emitted('confirmed')).toHaveLength(1);
  wrapper.unmount();
});
it('does not renew presentation on a routine reopen after cooldown', async () => {
  const wrapper = render('2026-01-01T00:00:00Z');
  expect(wrapper.text()).toContain('Exact assessment content');
  expect(mocks.prepare).not.toHaveBeenCalled();
  expect(mocks.confirm).not.toHaveBeenCalled();
  wrapper.unmount();
});
it('offers a newly selected repeat and retries an uncertain confirmation with the same cycle token', async () => {
  mocks.confirm
    .mockRejectedValueOnce(new TypeError('response lost'))
    .mockResolvedValueOnce({ presented_at: '2026-11-15T00:00:00Z' });
  const wrapper = render('2026-01-01T00:00:00Z', null);
  await visible();
  await visible();
  expect(mocks.confirm).toHaveBeenCalledTimes(1);
  await wrapper.get('button').trigger('click');
  await flushPromises();
  expect(mocks.prepare).toHaveBeenCalledTimes(1);
  expect(mocks.confirm.mock.calls[1]).toEqual(mocks.confirm.mock.calls[0]);
  wrapper.unmount();
});

it('does not confirm an assessment below the viewport until its actual evidence becomes visible', async () => {
  const wrapper = render();
  await visible();
  const geometry = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect');
  geometry.mockReturnValue({
    width: 200,
    height: 100,
    top: 2000,
    bottom: 2100,
    left: 0,
    right: 200,
    x: 0,
    y: 2000,
    toJSON() {},
  });
  await visible();
  expect(mocks.confirm).not.toHaveBeenCalled();
  geometry.mockReturnValue({
    width: 200,
    height: 100,
    top: 0,
    bottom: 100,
    left: 0,
    right: 200,
    x: 0,
    y: 0,
    toJSON() {},
  });
  (mocks.visible as (entries: { isIntersecting: boolean }[]) => void)([{ isIntersecting: false }]);
  await flushPromises();
  await visible();
  expect(mocks.confirm).toHaveBeenCalledTimes(1);
  wrapper.unmount();
});

it('ignores an old-session preparation result after identity changes', async () => {
  let complete: ((value: unknown) => void) | undefined;
  mocks.prepare.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const wrapper = render();
  await visible();
  await wrapper.setProps({ identity: 'different-account-session', historical: true });
  complete?.({
    recommendation_id: 'rec-1',
    assessment_revision_id: 'revision-1',
    offer_cycle_id: 'cycle-old-session',
    status: 'preparing',
    claim_token: 'old-token',
  });
  await flushPromises();
  await visible();
  expect(mocks.confirm).not.toHaveBeenCalled();
  expect(wrapper.emitted('confirmed')).toBeUndefined();
  wrapper.unmount();
});

it('renders refreshed canonical company state after confirming a newly selected offer', async () => {
  const wrapper = render(null);
  await visible();
  await visible();
  expect(mocks.confirm).toHaveBeenCalledTimes(1);
  await wrapper.setProps({
    recommendation: {
      ...item('2026-11-15T00:00:00Z'),
      company: { ...item().company, name: 'Updated Company' },
    },
  });
  expect(wrapper.text()).toContain('Updated Company');
  expect(wrapper.text()).not.toContain('Visible Company');
  expect(mocks.prepare).toHaveBeenCalledTimes(1);
  wrapper.unmount();
});

it('keeps new assessment content hidden when preparation has an uncertain result', async () => {
  mocks.prepare.mockRejectedValueOnce(new TypeError('response lost'));
  const wrapper = render();
  await visible();
  expect(wrapper.text()).toContain('Presentation is unconfirmed.');
  expect(wrapper.text()).not.toContain('Exact assessment content');
  expect(mocks.confirm).not.toHaveBeenCalled();
  wrapper.unmount();
});

it('prepares and confirms an unpresented repeat assessment after remount in a new session', async () => {
  const first = render('2026-01-01T00:00:00Z', null);
  first.unmount();
  const reopened = render('2026-01-01T00:00:00Z', null);
  expect(reopened.text()).not.toContain('Exact assessment content');
  expect(mocks.prepare).not.toHaveBeenCalled();
  await visible();
  expect(mocks.prepare).toHaveBeenCalledExactlyOnceWith(
    'rec-1',
    expect.objectContaining({ assessment_revision_id: 'revision-1' }),
  );
  expect(mocks.confirm).not.toHaveBeenCalled();
  await visible();
  expect(mocks.confirm).toHaveBeenCalledExactlyOnceWith('cycle-1', { claim_token: 'secret-token' });
  reopened.unmount();
});

it('does not reoffer the exact assessment already confirmed by another session or channel', async () => {
  const wrapper = render('2026-01-01T00:00:00Z', '2026-11-15T00:00:00Z');
  expect(wrapper.text()).toContain('Exact assessment content');
  await visible();
  expect(mocks.prepare).not.toHaveBeenCalled();
  expect(mocks.confirm).not.toHaveBeenCalled();
  wrapper.unmount();
});
