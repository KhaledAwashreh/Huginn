import { expect, it } from 'vitest';
import { matchDayLabel } from '@/features/matches/lib/matchDayLabel';

const now = new Date(2026, 9, 29, 12);

it('labels today and yesterday, then short dates with a year only when it differs', () => {
  expect(matchDayLabel(new Date(2026, 9, 29, 1), now)).toBe('Today');
  expect(matchDayLabel(new Date(2026, 9, 28, 23), now)).toBe('Yesterday');
  expect(matchDayLabel(new Date(2026, 9, 1), now)).toBe(
    new Date(2026, 9, 1).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
  );
  expect(matchDayLabel(new Date(2025, 9, 1), now)).toContain('2025');
});
