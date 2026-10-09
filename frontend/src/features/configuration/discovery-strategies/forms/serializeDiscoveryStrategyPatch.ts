import type { components } from '../../../../api/generated/schema';
import type { DiscoveryStrategyDraft } from './discoveryStrategyDraft';
export function serializeDiscoveryStrategyPatch(
  baseline: DiscoveryStrategyDraft,
  draft: DiscoveryStrategyDraft,
): components['schemas']['DiscoveryStrategyUpdateRequest'] {
  const patch: components['schemas']['DiscoveryStrategyUpdateRequest'] = {};
  if (baseline.name !== draft.name) patch.name = draft.name;
  if (baseline.service_offering_id !== draft.service_offering_id)
    patch.service_offering_id = draft.service_offering_id;
  if (baseline.ideal_client_profile_id !== draft.ideal_client_profile_id)
    patch.ideal_client_profile_id = draft.ideal_client_profile_id;
  if (baseline.is_active !== draft.is_active) patch.is_active = draft.is_active;
  return patch;
}
