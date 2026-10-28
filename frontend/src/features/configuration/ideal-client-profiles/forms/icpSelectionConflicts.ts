import type { IdealClientProfileDraft } from './idealClientProfileDraft';

export const industryIdentity = (value: string): string => value.trim().toLowerCase();

const countryAliases = new Map<string, string>();
const names = new Intl.DisplayNames(['en'], { type: 'region' });
for (let first = 65; first <= 90; first++) {
  for (let second = 65; second <= 90; second++) {
    const code = String.fromCharCode(first, second);
    const name = names.of(code);
    if (name && name !== code) {
      countryAliases.set(code.toLowerCase(), code);
      countryAliases.set(name.toLowerCase(), code);
    }
  }
}
// Apply aliases after the browser's reference names (which may include UK).
for (const [name, code] of [
  ['uk', 'GB'],
  ['gbr', 'GB'],
  ['united kingdom', 'GB'],
  ['usa', 'US'],
  ['united states of america', 'US'],
  ['united kingdom of great britain and northern ireland', 'GB'],
] as const)
  countryAliases.set(name, code);
export function countryIdentity(value: string): string {
  const normalized = value.trim().toLowerCase();
  return countryAliases.get(normalized) ?? normalized;
}

export function icpSelectionConflicts(draft: IdealClientProfileDraft): string[] {
  const industries = new Set(draft.industries.map((item) => industryIdentity(item.name)));
  const geographies = new Set(
    draft.geographies.map(
      (item) =>
        `${item.kind}:${item.kind === 'country' ? countryIdentity(item.value) : industryIdentity(item.value)}`,
    ),
  );
  return draft.exclusions.flatMap((item) => {
    const conflict =
      item.kind === 'industry'
        ? industries.has(industryIdentity(item.name))
        : item.kind === 'geography' &&
          geographies.has(
            `${item.geography.kind}:${item.geography.kind === 'country' ? countryIdentity(item.geography.value) : industryIdentity(item.geography.value)}`,
          );
    if (!conflict) return [];
    const value =
      item.kind === 'industry' ? item.name : item.kind === 'geography' ? item.geography.value : '';
    return [`${value} is both selected and excluded. Remove it from one list.`];
  });
}
