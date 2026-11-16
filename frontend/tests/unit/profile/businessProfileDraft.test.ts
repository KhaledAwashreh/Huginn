import { expect, it } from 'vitest';
import { createBusinessProfileDraft } from '@/features/profile/forms/businessProfileDraft';
import { serializeBusinessProfilePatch } from '@/features/profile/forms/serializeBusinessProfilePatch';
import type { BusinessProfile } from '@/features/profile/models/businessProfile';

const business: BusinessProfile = {
  id: 'business-1',
  owner_user_id: 'user-1',
  name: null,
  tagline: 'A careful tagline',
  website: null,
  location: 'Amman',
  description: null,
  capabilities: [{ name: 'Research' }],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

it('keeps unset Business fields blank and serializes only changed values', () => {
  const draft = createBusinessProfileDraft(business);
  expect(draft.name).toBe('');
  expect(draft.description).toBe('');

  draft.description = 'Product research for small teams.';
  expect(serializeBusinessProfilePatch(business, draft)).toEqual({
    description: 'Product research for small teams.',
  });
});

it('clears nullable fields explicitly and leaves unchanged capabilities out of unrelated patches', () => {
  const draft = createBusinessProfileDraft(business);
  draft.tagline = '';
  draft.description = 'A changed business description.';
  expect(serializeBusinessProfilePatch(business, draft)).toEqual({
    tagline: null,
    description: 'A changed business description.',
  });
});

it('serializes capability changes as names while preserving them on unrelated edits', () => {
  const unchanged = createBusinessProfileDraft(business);
  unchanged.location = 'Ramallah';
  expect(serializeBusinessProfilePatch(business, unchanged)).toEqual({ location: 'Ramallah' });

  const changed = createBusinessProfileDraft(business);
  changed.capabilities = ['Research', 'Product strategy'];
  expect(serializeBusinessProfilePatch(business, changed)).toEqual({
    capabilities: [{ name: 'Research' }, { name: 'Product strategy' }],
  });
});
