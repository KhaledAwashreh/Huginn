import type { BusinessProfileUpdateRequest } from '../api/updateBusinessProfile';
import type { BusinessProfileDraft } from './businessProfileDraft';
import type { BusinessProfile } from '../models/businessProfile';

export function serializeBusinessProfilePatch(
  baseline: BusinessProfile,
  draft: BusinessProfileDraft,
): BusinessProfileUpdateRequest | null {
  const patch: BusinessProfileUpdateRequest = {};
  for (const field of ['name', 'tagline', 'website', 'location', 'description'] as const) {
    const next = draft[field].trim();
    if (next !== (baseline[field] ?? '')) patch[field] = next || null;
  }

  const savedCapabilities = (baseline.capabilities ?? []).map(({ name }) => name);
  if (
    draft.capabilities.length !== savedCapabilities.length ||
    draft.capabilities.some((name, index) => name !== savedCapabilities[index])
  ) {
    patch.capabilities = draft.capabilities
      .map((name) => name.trim())
      .filter(Boolean)
      .map((name) => ({ name }));
  }

  return Object.keys(patch).length ? patch : null;
}
