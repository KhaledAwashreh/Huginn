import type { BusinessSetup, BusinessSetupDraft } from '../models/businessSetup';
import { createIdealClientProfileDraft } from '../../configuration/ideal-client-profiles/forms/idealClientProfileDraft';

export function businessSetupDraft(saved?: BusinessSetup): BusinessSetupDraft {
  return {
    business_name: saved?.business.name ?? '',
    your_name: saved ? `${saved.user.first_name} ${saved.user.last_name}`.trim() : '',
    service_description: saved?.service_offering?.description ?? '',
    ideal_client_profile: saved?.ideal_client_profile
      ? createIdealClientProfileDraft(saved.ideal_client_profile)
      : null,
  };
}
