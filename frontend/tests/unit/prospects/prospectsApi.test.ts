import { beforeEach, expect, it, vi } from 'vitest';
import { configureApiClient } from '../../../src/api/client';
import { changeProspectStage } from '../../../src/features/prospects/api/changeProspectStage';
import { closeProspect } from '../../../src/features/prospects/api/closeProspect';
import { correctProspectActivityTime } from '../../../src/features/prospects/api/correctProspectActivityTime';
import { getProspect } from '../../../src/features/prospects/api/getProspect';
import { listProspects } from '../../../src/features/prospects/api/listProspects';
import { recordProposalDraft } from '../../../src/features/prospects/api/recordProposalDraft';
import { reopenProspect } from '../../../src/features/prospects/api/reopenProspect';
import { setProspectFollowUp } from '../../../src/features/prospects/api/setProspectFollowUp';
import { clearProspectFollowUp } from '../../../src/features/prospects/api/clearProspectFollowUp';
import { updateProspectNotes } from '../../../src/features/prospects/api/updateProspectNotes';

beforeEach(() => {
  configureApiClient({ getCsrfToken: () => 'csrf-proof' });
  vi.restoreAllMocks();
});

it('searches the server-filtered full prospect page and resets no browser-side result scope', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  const controller = new AbortController();
  await listProspects(
    { stage: 'proposal_sent', search: '  Northstar.example ', offset: 50, limit: 25 },
    controller.signal,
  );
  expect(fetcher.mock.calls[0]?.[0]).toBe(
    '/api/v1/prospects?offset=50&limit=25&stage=proposal_sent&search=Northstar.example',
  );
  expect(fetcher.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
});

it('omits the stage filter for all stages and reads detail by encoded ID', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  await listProspects({ stage: 'all', search: '', offset: 0, limit: 25 });
  await getProspect('prospect/one');
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
    '/api/v1/prospects?offset=0&limit=25',
    '/api/v1/prospects/prospect%2Fone',
  ]);
});

it('sends each explicit lifecycle and history command to its own CSRF-protected endpoint', async () => {
  const fetcher = vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response('{}', { status: 200 }));
  const id = 'prospect-1';
  const version = 8;
  const key = 'command-key';
  await changeProspectStage(id, {
    expected_version: version,
    occurred_at: '2026-11-15T10:00:00Z',
    target_stage: 'contacted',
    request_key: key,
  });
  await closeProspect(id, {
    expected_version: version,
    occurred_at: '2026-11-15T10:00:00Z',
    reason: 'The opportunity ended.',
    request_key: key,
  });
  await reopenProspect(id, {
    expected_version: version,
    occurred_at: '2026-11-15T10:00:00Z',
    request_key: key,
  });
  await updateProspectNotes(id, {
    expected_version: version,
    occurred_at: '2026-11-15T10:00:00Z',
    replacement_notes: '',
    request_key: key,
  });
  await setProspectFollowUp(id, {
    expected_version: version,
    occurred_at: '2026-11-15T10:00:00Z',
    follow_up_at: '2026-11-20T09:00:00Z',
    request_key: key,
  });
  await clearProspectFollowUp(id, {
    expected_version: version,
    occurred_at: '2026-11-15T10:00:00Z',
    request_key: key,
  });
  await recordProposalDraft(id, {
    expected_version: version,
    occurred_at: '2026-11-15T10:00:00Z',
    summary: 'Draft scoped research proposal.',
    request_key: key,
  });
  await correctProspectActivityTime(id, {
    expected_version: version,
    expected_correction_head_id: null,
    original_activity_id: 'activity-1',
    replacement_occurred_at: '2026-11-02T10:00:00Z',
    request_key: key,
  });

  expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
    '/api/v1/prospects/prospect-1/stage',
    '/api/v1/prospects/prospect-1/close',
    '/api/v1/prospects/prospect-1/reopen',
    '/api/v1/prospects/prospect-1/notes',
    '/api/v1/prospects/prospect-1/follow-up',
    '/api/v1/prospects/prospect-1/clear-follow-up',
    '/api/v1/prospects/prospect-1/proposal-drafts',
    '/api/v1/prospects/prospect-1/activity-time-corrections',
  ]);
  for (const [, init] of fetcher.mock.calls) {
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('csrf-proof');
  }
  expect(fetcher.mock.calls[3]?.[1]?.body).toBe(
    JSON.stringify({
      expected_version: version,
      occurred_at: '2026-11-15T10:00:00Z',
      replacement_notes: '',
      request_key: key,
    }),
  );
  expect(fetcher.mock.calls[7]?.[1]?.body).toBe(
    JSON.stringify({
      expected_version: version,
      expected_correction_head_id: null,
      original_activity_id: 'activity-1',
      replacement_occurred_at: '2026-11-02T10:00:00Z',
      request_key: key,
    }),
  );
});
