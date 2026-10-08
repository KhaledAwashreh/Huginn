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
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
