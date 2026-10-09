import type { components } from '../../../../api/generated/schema';

export type ServiceOfferingDraft = Pick<
  components['schemas']['ServiceOfferingCreateRequest'],
  'name' | 'description'
>;
