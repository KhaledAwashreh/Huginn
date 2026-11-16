import { expect, it } from 'vitest';
import type { components } from '../../../src/api/generated/schema';
import {
  captureProspectCommand,
  createProspectCommandDraft,
  startProspectDraft,
} from '../../../src/features/prospects/models/prospectCommandDraft';

it('freezes the draft version when editing begins instead of adopting later query data', () => {
  const draft = createProspectCommandDraft('prospect-1');
  startProspectDraft(draft, 7);
  startProspectDraft(draft, 8);

  expect(draft.expectedVersion).toBe(7);
});

it('captures an immutable target and payload for exact uncertain retry', () => {
  const draft = createProspectCommandDraft('prospect-1');
  startProspectDraft(draft, 7);
  const expectedVersion = draft.expectedVersion;
  if (expectedVersion === null) throw new Error('Draft was not started');
  const request: components['schemas']['UpdateProspectNotesRequest'] = {
    expected_version: expectedVersion,
    occurred_at: '2026-11-15T10:00:00Z',
    replacement_notes: '',
    request_key: 'request-key-1',
  };
  const intent = captureProspectCommand(draft, 'business-user-session', 'notes', request);

  request.expected_version = 8;
  draft.prospectId = 'prospect-2';

  expect(intent).toMatchObject({
    identity: 'business-user-session',
    prospectId: 'prospect-1',
    kind: 'notes',
    request: {
      expected_version: 7,
      replacement_notes: '',
      request_key: 'request-key-1',
    },
  });
});
