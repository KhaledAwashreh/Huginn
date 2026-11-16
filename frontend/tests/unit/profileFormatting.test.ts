import { expect, it } from 'vitest';
import type { components } from '@/api/generated/schema';
import {
  engagementDates,
  icpDescription,
  websiteLabel,
  websiteUrl,
} from '@/features/profile/lib/profileFormatting';

const icp = {
  name: 'Early B2B',
  company_sizes: [{ band: '11-100' }],
  industries: [{ name: 'B2B' }, { name: 'Fintech' }],
  geographies: [{ kind: 'country', value: 'Netherlands' }],
  exclusions: [
    { kind: 'industry', name: 'Defense' },
    { kind: 'geography', geography: { kind: 'country', value: 'Canada' } },
    { kind: 'company', company_id: 'abc' },
  ],
} as components['schemas']['IdealClientProfileResponse'];

it('describes an ICP in one sentence from its fields', () => {
  expect(icpDescription(icp)).toBe(
    'B2B or Fintech companies with 11-100 employees in Netherlands, excluding Defense, Canada or A specific company.',
  );
  expect(
    icpDescription({ ...icp, industries: [], company_sizes: [], geographies: [], exclusions: [] }),
  ).toBe('Companies.');
});

it('shows client dates, with present for current work', () => {
  expect(engagementDates('2023-10', '', true)).toContain('Present');
  expect(engagementDates('', '', false)).toBe('');
});

it('links only web addresses', () => {
  expect(websiteUrl('fluke.design')).toBe('https://fluke.design/');
  expect(websiteUrl('javascript:alert(1)')).toBeNull();
  expect(websiteUrl('')).toBeNull();
  expect(websiteLabel('https://fluke.design/')).toBe('fluke.design');
});
