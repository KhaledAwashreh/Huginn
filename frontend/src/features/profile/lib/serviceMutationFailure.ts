import { ApiError } from '../../../api/apiError';

export type ServiceMutationFailure = { message: string; outcomeUncertain: boolean };

// Same rules as ServiceOfferingListPage: without a definite answer the change may have applied.
export function describeServiceMutationFailure(failure: unknown): ServiceMutationFailure {
  if (failure instanceof ApiError && failure.status === 409) {
    return {
      message:
        'This service is used by a discovery strategy. Update or remove that strategy reference first.',
      outcomeUncertain: false,
    };
  }
  if (failure instanceof ApiError && failure.status < 500) {
    return { message: failure.message, outcomeUncertain: false };
  }
  return {
    message: 'The outcome is uncertain. Refresh your services before trying again.',
    outcomeUncertain: true,
  };
}
