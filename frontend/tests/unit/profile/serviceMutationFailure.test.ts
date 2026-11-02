import { expect, it } from 'vitest';
import { ApiError } from '@/api/apiError';
import { describeServiceMutationFailure } from '@/features/profile/lib/serviceMutationFailure';

it('explains that a 409 means a strategy uses the service', () => {
  const described = describeServiceMutationFailure(new ApiError(409, 'referenced', 'Conflict'));
  expect(described.message).toContain('used by a discovery strategy');
  expect(described.outcomeUncertain).toBe(false);
});

it('keeps the API message for other definite rejections', () => {
  expect(describeServiceMutationFailure(new ApiError(422, 'invalid', 'Check this.'))).toEqual({
    message: 'Check this.',
    outcomeUncertain: false,
  });
});

it.each([
  ['a 5xx', new ApiError(503, 'request_failed', 'Unavailable')],
  ['a network failure', new TypeError('Failed to fetch')],
])('treats %s as an uncertain outcome without its raw message', (_name, failure) => {
  const described = describeServiceMutationFailure(failure);
  expect(described.outcomeUncertain).toBe(true);
  expect(described.message).toContain('uncertain');
  expect(described.message).not.toContain('Failed to fetch');
});
