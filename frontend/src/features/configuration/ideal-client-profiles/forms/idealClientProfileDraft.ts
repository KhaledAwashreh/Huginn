import type { components } from '../../../../api/generated/schema';

export type IdealClientProfileDraft = Pick<
  components['schemas']['IdealClientProfileCreateRequest'],
  'name'
> & {
  industries: components['schemas']['Industry'][];
  company_sizes: components['schemas']['CompanySize'][];
  geographies: (
    components['schemas']['CountryGeography'] | components['schemas']['RegionGeography']
  )[];
  exclusions: (
    | components['schemas']['CompanyExclusion']
    | components['schemas']['IndustryExclusion']
    | components['schemas']['GeographyExclusion']
  )[];
};
