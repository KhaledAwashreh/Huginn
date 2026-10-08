export interface ResetPasswordDraft {
  new_password: string;
}

const PASSWORD_LENGTH_ERROR = 'Use 8 to 16 characters.';
const PASSWORD_CONTENT_ERROR =
  'Use at least one letter, one digit, and one punctuation or symbol. Control characters are not allowed.';

export function validateLifecyclePassword(password: string): string | null {
  const codePoints = Array.from(password);
  if (codePoints.length < 8 || codePoints.length > 16) return PASSWORD_LENGTH_ERROR;
  if (/\p{C}/u.test(password)) return PASSWORD_CONTENT_ERROR;
  if (!/\p{L}/u.test(password) || !/[0-9]/.test(password) || !/[\p{P}\p{S}]/u.test(password))
    return PASSWORD_CONTENT_ERROR;
  return null;
}
