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

// Map each row to plain values: selection controls may retain reactive row objects.
export function createIdealClientProfileDraft(
  source?: IdealClientProfileDraft | null,
): IdealClientProfileDraft {
  return {
    name: source?.name ?? '',
    industries: source?.industries.map(({ name }) => ({ name })) ?? [],
    company_sizes: source?.company_sizes.map(({ band }) => ({ band })) ?? [],
    geographies: source?.geographies.map(({ kind, value }) => ({ kind, value })) ?? [],
    exclusions:
      source?.exclusions.map((item) =>
        item.kind === 'company'
          ? { kind: item.kind, company_id: item.company_id }
          : item.kind === 'industry'
            ? { kind: item.kind, name: item.name }
            : {
                kind: item.kind,
                geography: { kind: item.geography.kind, value: item.geography.value },
              },
      ) ?? [],
  };
}
