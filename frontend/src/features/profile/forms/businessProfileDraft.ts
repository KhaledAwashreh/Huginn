import type { BusinessProfile } from '../models/businessProfile';

export type BusinessProfileDraft = {
  name: string;
  tagline: string;
  website: string;
  location: string;
  description: string;
  capabilities: string[];
};

export function createBusinessProfileDraft(profile: BusinessProfile): BusinessProfileDraft {
  return {
    name: profile.name ?? '',
    tagline: profile.tagline ?? '',
    website: profile.website ?? '',
    location: profile.location ?? '',
    description: profile.description ?? '',
    capabilities: (profile.capabilities ?? []).map(({ name }) => name),
  };
}
