import type { components } from '../../../../api/generated/schema';
import { type AccountDraft, type AccountResponse } from './accountDraft';

type AccountPatch = components['schemas']['UserUpdateRequest'];

export function serializeAccountPatch(
  baseline: AccountResponse,
  draft: AccountDraft,
): AccountPatch {
  const patch: AccountPatch = {};
  if (draft.first_name !== baseline.first_name) patch.first_name = draft.first_name.trim();
  if (draft.last_name !== baseline.last_name) patch.last_name = draft.last_name.trim();
  if (draft.email !== baseline.email) patch.email = draft.email.trim();
  if (draft.phone_number !== baseline.phone_number) patch.phone_number = draft.phone_number.trim();
  if (draft.country_of_residence !== baseline.country_of_residence)
    patch.country_of_residence = draft.country_of_residence;
  if (draft.timezone !== (baseline.timezone ?? '')) patch.timezone = draft.timezone.trim() || null;
  return patch;
}
