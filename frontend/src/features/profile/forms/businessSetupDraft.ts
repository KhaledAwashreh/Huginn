import type { BusinessSetup, BusinessSetupDraft } from '../models/businessSetup';

export const emptyIcp = () => ({
  name: '',
  industries: [],
  company_sizes: [],
  geographies: [],
  exclusions: [],
});
export function businessSetupDraft(saved?: BusinessSetup): BusinessSetupDraft {
  const icp = saved?.ideal_client_profile;
  return {
    business_name: saved?.business.name ?? '',
    your_name: saved ? `${saved.user.first_name} ${saved.user.last_name}`.trim() : '',
    email: saved?.user.email ?? '',
    service_description: saved?.service_offering?.description ?? '',
    ideal_client_profile: icp
      ? {
          name: icp.name,
          industries: icp.industries.map(({ name }) => ({ name })),
          company_sizes: icp.company_sizes.map(({ band }) => ({ band })),
          geographies: icp.geographies.map(({ kind, value }) => ({ kind, value })),
          exclusions: icp.exclusions.map((item) =>
            item.kind === 'company'
              ? { kind: item.kind, company_id: item.company_id }
              : item.kind === 'industry'
                ? { kind: item.kind, name: item.name }
                : {
                    kind: item.kind,
                    geography: { kind: item.geography.kind, value: item.geography.value },
                  },
          ),
        }
      : null,
  };
}
