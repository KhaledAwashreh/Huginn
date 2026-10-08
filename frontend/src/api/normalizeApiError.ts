import { ApiError, type FieldError } from './apiError';

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export function normalizeApiError(status: number, value: unknown): ApiError {
  const fallback =
    status >= 500
      ? 'The service is unavailable. Try again.'
      : status === 401
        ? 'Sign in to continue.'
        : status === 403
          ? 'This action was forbidden. Reload before trying again.'
          : status === 429
            ? 'Too many attempts. Wait before trying again.'
            : status === 404
              ? 'This item is no longer available. Reload the page to continue.'
              : status === 409
                ? 'These details conflict with an existing record. Check your entries and try again.'
                : status === 422
                  ? 'Check the information you entered and try again.'
                  : 'Reload the page and try again. If the problem continues, try again later.';
  if (status >= 500 || !record(value)) return new ApiError(status, 'request_failed', fallback);
  if (record(value.error) && typeof value.error.message === 'string') {
    return new ApiError(
      status,
      typeof value.error.code === 'string' ? value.error.code : 'request_failed',
      status === 403 ||
        status === 429 ||
        /^\s*(?:the )?request could not be completed\.?\s*$/i.test(value.error.message)
        ? fallback
        : value.error.message,
    );
  }
  const fields: FieldError[] = [];
  if (status === 422 && Array.isArray(value.detail)) {
    for (const item of value.detail) {
      if (!record(item) || !Array.isArray(item.loc) || typeof item.msg !== 'string') continue;
      const path = item.loc.filter(
        (part): part is string | number => typeof part === 'string' || typeof part === 'number',
      );
      if (path[0] === 'body') path.shift();
      fields.push({ path, message: item.msg });
    }
  }
  return new ApiError(
    status,
    'request_failed',
    fields.length ? 'Check the highlighted fields.' : fallback,
    fields,
  );
}
