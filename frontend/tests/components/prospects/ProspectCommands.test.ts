import { flushPromises, mount } from '@vue/test-utils';
import { reactive } from 'vue';
import PrimeVue from 'primevue/config';
import { beforeEach, expect, it, vi } from 'vitest';
import ProspectLifecycleActions from '../../../src/features/prospects/components/ProspectLifecycleActions.vue';
import ProspectNotesEditor from '../../../src/features/prospects/components/ProspectNotesEditor.vue';
import ProspectFollowUpEditor from '../../../src/features/prospects/components/ProspectFollowUpEditor.vue';
import ProspectActivityTimeCorrection from '../../../src/features/prospects/components/ProspectActivityTimeCorrection.vue';
import ProspectHistory from '../../../src/features/prospects/components/ProspectHistory.vue';
import type {
  ProspectCommandDraft,
  ProspectCommandSubmission,
} from '../../../src/features/prospects/models/prospectCommandDraft';
import { createProspectCommandDraft } from '../../../src/features/prospects/models/prospectCommandDraft';
import { activity, prospect } from './prospectFixture';

function button(wrapper: ReturnType<typeof mount>, label: string) {
  const result = wrapper.findAll('button').find((candidate) => candidate.text().trim() === label);
  if (!result) throw new Error(`Button not found: ${label}`);
  return result;
}
function draft(): ProspectCommandDraft {
  return reactive(createProspectCommandDraft('prospect-1'));
}
const plugins = { global: { plugins: [PrimeVue] } };

beforeEach(() => {
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'request-key-1') });
});

it('requires a reason for backward stage changes and submits the frozen prospect version', async () => {
  const state = draft();
  const wrapper = mount(ProspectLifecycleActions, {
    props: { prospect: prospect(), draft: state, disabled: false },
    ...plugins,
  });
  await button(wrapper, 'Move back to contacted').trigger('click');
  await wrapper.get('input[type="datetime-local"]').setValue('2026-10-28T09:30');
  const save = button(wrapper, 'Save stage change');
  expect((save.element as HTMLButtonElement).disabled).toBe(true);
  await wrapper.get('textarea').setValue('The prospect clarified timing.');
  await wrapper.get('form').trigger('submit');
  await flushPromises();

  expect(wrapper.emitted('command')?.[0]?.[0]).toMatchObject({
    kind: 'stage',
    request: {
      expected_version: 4,
      target_stage: 'contacted',
      occurred_at: new Date('2026-10-28T09:30').toISOString(),
      reason: 'The prospect clarified timing.',
      request_key: 'request-key-1',
    },
  });
  state.expectedVersion = 9;
  expect((wrapper.emitted('command')?.[0]?.[0] as ProspectCommandSubmission).request).toMatchObject(
    {
      expected_version: 4,
    },
  );
});

it('does not expose close for a won prospect and reopens closed prospect without choosing its target', async () => {
  const won = mount(ProspectLifecycleActions, {
    props: {
      prospect: prospect({ stage: 'won_client', last_active_stage: null }),
      draft: draft(),
      disabled: false,
    },
    ...plugins,
  });
  expect(won.text()).not.toContain('Close prospect');

  const state = draft();
  const closed = mount(ProspectLifecycleActions, {
    props: {
      prospect: prospect({ stage: 'closed', last_active_stage: 'proposal_sent' }),
      draft: state,
      disabled: false,
    },
    ...plugins,
  });
  await button(closed, 'Reopen to last active stage').trigger('click');
  expect(closed.emitted('command')?.[0]?.[0]).toMatchObject({
    kind: 'reopen',
    request: { expected_version: 4, request_key: 'request-key-1' },
  });
  expect(state.expectedVersion).toBe(4);
});

it('requires a reason when closing an active prospect', async () => {
  const wrapper = mount(ProspectLifecycleActions, {
    props: { prospect: prospect({ stage: 'contacted' }), draft: draft(), disabled: false },
    ...plugins,
  });
  await button(wrapper, 'Close prospect').trigger('click');
  const confirm = button(wrapper, 'Confirm close');
  expect((confirm.element as HTMLButtonElement).disabled).toBe(true);
  await wrapper.get('textarea').setValue('The Company ended the discussion.');
  await wrapper.get('form').trigger('submit');
  expect(wrapper.emitted('command')?.[0]?.[0]).toMatchObject({
    kind: 'close',
    request: {
      expected_version: 4,
      reason: 'The Company ended the discussion.',
      request_key: 'request-key-1',
    },
  });
});

it('replaces notes with empty text to clear the memo and retains optimistic version', async () => {
  const state = draft();
  const wrapper = mount(ProspectNotesEditor, {
    props: { prospect: prospect(), draft: state, disabled: false },
    ...plugins,
  });
  await button(wrapper, 'Edit notes').trigger('click');
  await wrapper.get('textarea').setValue('');
  await wrapper.get('form').trigger('submit');
  expect(wrapper.emitted('command')?.[0]?.[0]).toMatchObject({
    kind: 'notes',
    request: { expected_version: 4, replacement_notes: '', request_key: 'request-key-1' },
  });
});

it('sets and clears reminder only through explicit commands', async () => {
  const state = draft();
  const wrapper = mount(ProspectFollowUpEditor, {
    props: { prospect: prospect(), draft: state, disabled: false },
    ...plugins,
  });
  await button(wrapper, 'Set reminder').trigger('click');
  await wrapper.get('input[type="datetime-local"]').setValue('2026-11-20T09:00');
  await wrapper.get('form').trigger('submit');
  expect(wrapper.emitted('command')?.[0]?.[0]).toMatchObject({
    kind: 'follow_up',
    request: {
      expected_version: 4,
      follow_up_at: new Date('2026-11-20T09:00').toISOString(),
    },
  });

  const existing = mount(ProspectFollowUpEditor, {
    props: {
      prospect: prospect({ follow_up_at: '2026-11-20T09:00:00Z' }),
      draft: draft(),
      disabled: false,
    },
    ...plugins,
  });
  await button(existing, 'Clear reminder').trigger('click');
  expect(existing.emitted('command')?.[0]?.[0]).toMatchObject({ kind: 'clear_follow_up' });
});

it('records proposal draft as an activity-only command and offers no send action', async () => {
  const state = draft();
  const wrapper = mount(ProspectLifecycleActions, {
    props: { prospect: prospect({ stage: 'in_conversation' }), draft: state, disabled: false },
    ...plugins,
  });
  await button(wrapper, 'Record proposal draft').trigger('click');
  expect(wrapper.text()).toContain('does not change the prospect stage or send a message');
  await wrapper.get('textarea').setValue('Research proposal outline.');
  await wrapper.get('form').trigger('submit');
  expect(wrapper.emitted('command')?.[0]?.[0]).toMatchObject({
    kind: 'proposal_draft',
    request: {
      expected_version: 4,
      summary: 'Research proposal outline.',
      request_key: 'request-key-1',
    },
  });
  expect(wrapper.text()).not.toContain('Send proposal');
});

it('corrects only an original activity using the pinned version and correction head', async () => {
  const state = draft();
  const original = activity({ correction_head_id: 'correction-head-2', correction_sequence: 2 });
  const wrapper = mount(ProspectActivityTimeCorrection, {
    props: { activity: original, prospectVersion: 4, draft: state, disabled: false },
    ...plugins,
  });
  await button(wrapper, 'Correct occurrence time').trigger('click');
  await wrapper.get('input[type="datetime-local"]').setValue('2026-10-31T10:30');
  await wrapper.get('form').trigger('submit');
  expect(wrapper.emitted('command')?.[0]?.[0]).toMatchObject({
    expected_version: 4,
    expected_correction_head_id: 'correction-head-2',
    original_activity_id: 'activity-1',
    replacement_occurred_at: new Date('2026-10-31T10:30').toISOString(),
    request_key: 'request-key-1',
  });

  const correction = activity({
    id: 'correction-1',
    kind: 'correction',
    correction_of_id: 'activity-1',
  });
  const correctionView = mount(ProspectActivityTimeCorrection, {
    props: { activity: correction, prospectVersion: 4, draft: draft(), disabled: false },
    ...plugins,
  });
  expect(correctionView.text()).toBe('');
  expect(correctionView.find('button').exists()).toBe(false);
});

it('keeps the original event and appended correction visible in chronological history', () => {
  const original = activity({ correction_head_id: 'correction-1', correction_sequence: 1 });
  const correction = activity({
    id: 'correction-1',
    kind: 'correction',
    correction_of_id: 'activity-1',
    correction_sequence: 1,
    occurred_at: '2026-11-02T10:00:00Z',
    effective_occurred_at: '2026-11-02T10:00:00Z',
    recorded_at: '2026-11-02T10:01:00Z',
    payload: {
      prior: '2026-11-01T10:00:00Z',
      replacement: '2026-10-31T10:30:00Z',
      correction_sequence: 1,
    },
  });
  const wrapper = mount(ProspectHistory, {
    props: {
      prospect: prospect({ activities: [correction, original] }),
      draft: draft(),
      disabled: false,
    },
    ...plugins,
  });
  expect(wrapper.text()).toContain('Stage changed');
  expect(wrapper.text()).toContain('Activity time corrected');
  expect(wrapper.text()).toContain(
    'Correction 1: occurred time changed from 2026-11-01T10:00:00Z to 2026-10-31T10:30:00Z',
  );
  expect(wrapper.findAll('li').length).toBe(2);
});
