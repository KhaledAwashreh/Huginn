import type { components } from '../../../../api/generated/schema';

export type ProfessionalProfileResponse = components['schemas']['ProfessionalProfileResponse'];
export type SkillDraft = { name: string };
export type ExperienceDraft = {
  organization: string;
  role: string;
  summary: string;
  start_month: string;
  end_month: string;
  is_current: boolean;
};
export type PreviousProjectDraft = { name: string; description: string };
export type ProfessionalProfileDraft = {
  headline: string;
  professional_summary: string;
  skills: SkillDraft[];
  experience: ExperienceDraft[];
  previous_projects: PreviousProjectDraft[];
};

export function createProfessionalProfileDraft(
  profile: ProfessionalProfileResponse,
): ProfessionalProfileDraft {
  return {
    headline: profile.headline ?? '',
    professional_summary: profile.professional_summary ?? '',
    skills: profile.skills.map(({ name }) => ({ name })),
    experience: profile.experience.map((item) => ({
      organization: item.organization,
      role: item.role,
      summary: item.summary ?? '',
      start_month: item.start_month ?? '',
      end_month: item.end_month ?? '',
      is_current: item.is_current,
    })),
    previous_projects: profile.previous_projects.map(({ name, description }) => ({
      name,
      description,
    })),
  };
}
