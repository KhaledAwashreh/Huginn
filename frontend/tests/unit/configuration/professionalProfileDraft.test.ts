import { describe, expect, it } from 'vitest';
import { createProfessionalProfileDraft } from '../../../src/features/configuration/professional-profile/forms/professionalProfileDraft';
import { serializeProfessionalProfilePatch } from '../../../src/features/configuration/professional-profile/forms/serializeProfessionalProfilePatch';
import type { components } from '../../../src/api/generated/schema';

type Profile = components['schemas']['ProfessionalProfileResponse'];

const profile: Profile = {
  id: 'profile-1',
  user_id: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  headline: 'Engineer',
  professional_summary: null,
  skills: [{ name: 'Python' }, { name: 'Python' }],
  experience: [
    {
      organization: 'Example',
      role: 'Engineer',
      summary: null,
      start_month: '2020-01',
      end_month: null,
      is_current: true,
    },
  ],
  previous_projects: [{ name: 'Compiler', description: 'Built a compiler' }],
};

describe('professional profile draft', () => {
  it('preserves order and duplicate values and omits unchanged response metadata', () => {
    const draft = createProfessionalProfileDraft(profile);
    expect(serializeProfessionalProfilePatch(profile, draft)).toEqual({});
    expect(draft.skills).toEqual([{ name: 'Python' }, { name: 'Python' }]);
  });

  it('uses null for cleared nullable text and arrays for cleared collections', () => {
    const draft = { ...createProfessionalProfileDraft(profile), headline: '', skills: [] };
    expect(serializeProfessionalProfilePatch(profile, draft)).toEqual({
      headline: null,
      skills: [],
    });
  });
});
