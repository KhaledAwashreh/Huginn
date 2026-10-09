export interface FieldError {
  path: (string | number)[];
  message: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly fields: FieldError[] = [],
    public readonly details: readonly Record<string, unknown>[] = [],
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
