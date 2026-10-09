export type PasswordChangeDraft = { current_password: string; new_password: string };

export function createPasswordChangeDraft(): PasswordChangeDraft {
  return { current_password: '', new_password: '' };
}
