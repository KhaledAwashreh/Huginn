import { describe, expect, it } from 'vitest';
import { createAccountDraft } from '../../../src/features/configuration/account/forms/accountDraft';
import { serializeAccountPatch } from '../../../src/features/configuration/account/forms/serializeAccountPatch';
import type { components } from '../../../src/api/generated/schema';

type User = components['schemas']['UserResponse'];

const user: User = {
  id: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  first_name: 'Ada',
  last_name: 'Lovelace',
  email: 'ada@example.com',
  phone_number: '+12025550123',
  country_of_residence: 'GB',
  timezone: 'Europe/London',
};

describe('account draft', () => {
  it('keeps an E.164 phone unchanged when residence country has another calling code', () => {
    const draft = createAccountDraft(user);
    expect(draft.phone_number).toBe('+12025550123');
    expect(serializeAccountPatch(user, draft)).toEqual({});
  });

  it('sends only changed fields and explicitly clears nullable timezone', () => {
    const draft = { ...createAccountDraft(user), first_name: 'Augusta', timezone: '' };
    expect(serializeAccountPatch(user, draft)).toEqual({ first_name: 'Augusta', timezone: null });
  });
});
