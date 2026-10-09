import { describe, expect, it } from 'vitest';
import {
  mergeCollectedExclusions,
  mergeCollectedValues,
} from '../../../src/features/configuration/ideal-client-profiles/forms/collectedOptionSelection';

describe('collected option selection', () => {
  it('keeps saved duplicate and legacy rows in order until their values are deselected', () => {
    const current = [{ name: 'Legacy' }, { name: 'Collected' }, { name: 'Legacy' }];
    expect(
      mergeCollectedValues(
        current,
        ['Legacy', 'Collected', 'Added'],
        (row) => row.name,
        (name) => ({ name }),
      ),
    ).toEqual([{ name: 'Legacy' }, { name: 'Collected' }, { name: 'Legacy' }, { name: 'Added' }]);
  });

  it('changes only one exclusion category and retains all other categories in original order', () => {
    type Row =
      | { kind: 'industry'; name: string }
      | { kind: 'company'; company_id: string }
      | { kind: 'geography'; geography: { kind: 'country' | 'region'; value: string } };
    const current: Row[] = [
      { kind: 'company', company_id: 'first' },
      { kind: 'industry', name: 'Legacy' },
      { kind: 'geography', geography: { kind: 'region', value: 'Old region' } },
      { kind: 'industry', name: 'Legacy' },
    ];
    expect(
      mergeCollectedExclusions(
        current,
        ['Legacy', 'New industry'],
        (row) => (row.kind === 'industry' ? row.name : undefined),
        (name) => ({ kind: 'industry' as const, name }),
      ),
    ).toEqual([
      { kind: 'company', company_id: 'first' },
      { kind: 'industry', name: 'Legacy' },
      { kind: 'geography', geography: { kind: 'region', value: 'Old region' } },
      { kind: 'industry', name: 'Legacy' },
      { kind: 'industry', name: 'New industry' },
    ]);
  });
});
