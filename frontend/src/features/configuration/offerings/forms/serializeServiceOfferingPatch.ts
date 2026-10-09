import type { components } from '../../../../api/generated/schema';
import type { ServiceOfferingDraft } from './serviceOfferingDraft';

export function serializeServiceOfferingPatch(
  baseline: ServiceOfferingDraft,
  draft: ServiceOfferingDraft,
): components['schemas']['ServiceOfferingUpdateRequest'] | null {
  const patch: components['schemas']['ServiceOfferingUpdateRequest'] = {};
  if (baseline.name !== draft.name) patch.name = draft.name;
  if (baseline.description !== draft.description) patch.description = draft.description;
  return Object.keys(patch).length ? patch : null;
}
