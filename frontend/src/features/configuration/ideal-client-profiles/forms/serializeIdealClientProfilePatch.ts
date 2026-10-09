import type { components } from '../../../../api/generated/schema';
import type { IdealClientProfileDraft } from './idealClientProfileDraft';

export function serializeIdealClientProfilePatch(
  baseline: IdealClientProfileDraft,
  draft: IdealClientProfileDraft,
): components['schemas']['IdealClientProfileUpdateRequest'] | null {
  const patch: components['schemas']['IdealClientProfileUpdateRequest'] = {};
  if (baseline.name !== draft.name) patch.name = draft.name;
  if (JSON.stringify(baseline.industries) !== JSON.stringify(draft.industries))
    patch.industries = draft.industries;
  if (JSON.stringify(baseline.company_sizes) !== JSON.stringify(draft.company_sizes))
    patch.company_sizes = draft.company_sizes;
  if (JSON.stringify(baseline.geographies) !== JSON.stringify(draft.geographies))
    patch.geographies = draft.geographies;
  if (JSON.stringify(baseline.exclusions) !== JSON.stringify(draft.exclusions))
    patch.exclusions = draft.exclusions;
  return Object.keys(patch).length ? patch : null;
}
