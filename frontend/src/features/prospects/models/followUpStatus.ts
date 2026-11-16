export type FollowUpStatus = 'none' | 'upcoming' | 'due';

export function followUpStatus(
  followUpAt: string | null | undefined,
  now: Date | number,
): FollowUpStatus {
  if (!followUpAt) return 'none';
  const nowMilliseconds = typeof now === 'number' ? now : now.getTime();
  return new Date(followUpAt).getTime() <= nowMilliseconds ? 'due' : 'upcoming';
}
