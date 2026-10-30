import { expect, it } from 'vitest';
import {
  countryIdentity,
  icpSelectionConflicts,
} from '../../../src/features/configuration/ideal-client-profiles/forms/icpSelectionConflicts';

it('detects industry and country alias conflicts without treating other exclusions as conflicts', () => {
  const draft = {
    name: 'ICP',
    industries: [{ name: 'Analytics' }],
    company_sizes: [],
    geographies: [{ kind: 'country' as const, value: 'USA' }],
    exclusions: [
      { kind: 'industry' as const, name: ' analytics ' },
      {
        kind: 'geography' as const,
        geography: { kind: 'country' as const, value: 'United States' },
      },
    ],
  };
  expect(icpSelectionConflicts(draft)).toHaveLength(2);
  expect(countryIdentity('UK')).toBe(countryIdentity('United Kingdom'));
  expect(countryIdentity('UK')).toBe(countryIdentity('GB'));
  expect(countryIdentity('US')).toBe(countryIdentity('United States of America'));
  expect(
    icpSelectionConflicts({ ...draft, exclusions: [{ kind: 'industry', name: 'Retail' }] }),
  ).toEqual([]);
});

it('normalizes generic ISO alpha-3 country aliases', () => {
  expect(countryIdentity('DEU')).toBe(countryIdentity('Germany'));
  expect(countryIdentity('NGA')).toBe(countryIdentity('Nigeria'));
});
