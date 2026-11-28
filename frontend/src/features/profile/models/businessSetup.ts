import type { components } from '../../../api/generated/schema';
import type { IdealClientProfileDraft } from '../../configuration/ideal-client-profiles/forms/idealClientProfileDraft';

export type BusinessSetup = components['schemas']['BusinessSetupResponse'];
export interface BusinessSetupDraft {
  business_name: string;
  your_name: string;
  service_description: string;
  ideal_client_profile: IdealClientProfileDraft | null;
}
export type BusinessSetupRequest = components['schemas']['BusinessSetupUpdateRequest'];
