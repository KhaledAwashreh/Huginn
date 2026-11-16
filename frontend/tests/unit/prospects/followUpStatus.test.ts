import { expect, it } from 'vitest';
import { followUpStatus } from '../../../src/features/prospects/models/followUpStatus';

const now = new Date('2026-11-16T12:00:00.000Z');

it('classifies an unset follow-up separately', () => {
  expect(followUpStatus(null, now)).toBe('none');
});

it('marks a follow-up due at its exact timestamp and after it', () => {
  expect(followUpStatus('2026-11-16T12:00:00.000Z', now)).toBe('due');
  expect(followUpStatus('2026-11-16T11:59:59.000Z', now)).toBe('due');
});

it('keeps a future follow-up upcoming', () => {
  expect(followUpStatus('2026-11-16T12:00:01.000Z', now)).toBe('upcoming');
});
