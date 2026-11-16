import { flushPromises, mount } from '@vue/test-utils';
import PrimeVue from 'primevue/config';
import { afterEach, expect, it, vi } from 'vitest';
import ProspectList from '../../../src/features/prospects/components/ProspectList.vue';
import ProspectFollowUpEditor from '../../../src/features/prospects/components/ProspectFollowUpEditor.vue';
import { createProspectCommandDraft } from '../../../src/features/prospects/models/prospectCommandDraft';
import { prospect } from './prospectFixture';

afterEach(() => {
  vi.useRealTimers();
});

it('updates list and detail status at the due boundary without issuing commands', async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-16T11:59:59.000Z'));
  const item = prospect({ follow_up_at: '2026-11-16T12:00:00.000Z' });
  const list = mount(ProspectList, {
    props: {
      page: { items: [item], offset: 0, limit: 25, has_more: false },
      selectedId: item.id,
      loading: false,
      failed: false,
      fetching: false,
      offset: 0,
      pageSize: 25,
    },
    global: { plugins: [PrimeVue] },
  });
  const detail = mount(ProspectFollowUpEditor, {
    props: {
      prospect: item,
      draft: createProspectCommandDraft(item.id),
      disabled: false,
    },
    attrs: { onCommand: vi.fn() },
    global: { plugins: [PrimeVue] },
  });

  expect(list.text()).toContain('Upcoming');
  expect(detail.text()).toContain('Upcoming');
  vi.advanceTimersByTime(1_000);
  await flushPromises();

  expect(list.text()).toContain('Due');
  expect(detail.text()).toContain('Due');
  expect(detail.emitted('command')).toBeUndefined();
  list.unmount();
  detail.unmount();
  expect(vi.getTimerCount()).toBe(0);
});

it('refreshes due status when the page returns to the foreground and clears when unset', async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-16T12:00:00.000Z'));
  const upcoming = prospect({ follow_up_at: '2026-11-16T12:01:00.000Z' });
  const editor = mount(ProspectFollowUpEditor, {
    props: { prospect: upcoming, draft: createProspectCommandDraft(upcoming.id), disabled: false },
    global: { plugins: [PrimeVue] },
  });
  expect(editor.text()).toContain('Upcoming');
  vi.setSystemTime(new Date('2026-11-16T12:01:00.000Z'));
  document.dispatchEvent(new Event('visibilitychange'));
  await flushPromises();
  expect(editor.text()).toContain('Due');
  expect(editor.emitted('command')).toBeUndefined();
  await editor.setProps({ prospect: prospect({ follow_up_at: null }) });
  expect(editor.text()).not.toContain('Due');
  expect(editor.text()).not.toContain('Upcoming');
  expect(editor.text()).toContain('No reminder is set.');
  editor.unmount();
});
