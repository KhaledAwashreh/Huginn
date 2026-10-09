import type { components } from '../../../../api/generated/schema';
import type {
  ProfessionalProfileDraft,
  ProfessionalProfileResponse,
} from './professionalProfileDraft';

type ProfessionalProfilePatch = components['schemas']['ProfessionalProfileUpdateRequest'];

export function serializeProfessionalProfilePatch(
  baseline: ProfessionalProfileResponse,
  draft: ProfessionalProfileDraft,
): ProfessionalProfilePatch {
  const patch: ProfessionalProfilePatch = {};
  if (draft.headline !== (baseline.headline ?? '')) patch.headline = draft.headline.trim() || null;
  if (draft.professional_summary !== (baseline.professional_summary ?? ''))
    patch.professional_summary = draft.professional_summary.trim() || null;
  const skills = draft.skills.map(({ name }) => ({ name: name.trim() }));
  if (JSON.stringify(skills) !== JSON.stringify(baseline.skills)) patch.skills = skills;
  const experience = draft.experience.map((item) => ({
    organization: item.organization.trim(),
    role: item.role.trim(),
    summary: item.summary.trim() || null,
    start_month: item.start_month || null,
    end_month: item.end_month || null,
    is_current: item.is_current,
  }));
  if (
    JSON.stringify(experience) !==
    JSON.stringify(
      baseline.experience.map((item) => ({
        organization: item.organization,
        role: item.role,
        summary: item.summary,
        start_month: item.start_month,
        end_month: item.end_month,
        is_current: item.is_current,
      })),
    )
  )
    patch.experience = experience;
  const previousProjects = draft.previous_projects.map(({ name, description }) => ({
    name: name.trim(),
    description: description.trim(),
  }));
  if (JSON.stringify(previousProjects) !== JSON.stringify(baseline.previous_projects))
    patch.previous_projects = previousProjects;
  return patch;
}
