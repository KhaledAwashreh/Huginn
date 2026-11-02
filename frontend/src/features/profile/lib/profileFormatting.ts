import type { components } from '../../../api/generated/schema';

type Icp = components['schemas']['IdealClientProfileResponse'];

function spokenList(items: string[]): string {
  if (items.length < 2) return items.join('');
  return `${items.slice(0, -1).join(', ')} or ${items.at(-1)}`;
}

// One readable sentence built only from the ICP's own fields.
export function icpDescription(icp: Icp): string {
  const industries = spokenList(icp.industries.map((item) => item.name));
  const sizes = spokenList(icp.company_sizes.map((item) => item.band));
  const places = spokenList(icp.geographies.map((item) => item.value));
  const avoiding = spokenList(icpExclusions(icp));
  return [
    industries ? `${industries} companies` : 'Companies',
    sizes && `with ${sizes} employees`,
    places && `in ${places}`,
  ]
    .filter(Boolean)
    .join(' ')
    .concat(avoiding ? `, excluding ${avoiding}.` : '.');
}

function monthLabel(month: string): string {
  const [year, monthNumber] = month.split('-').map(Number);
  if (!year || !monthNumber) return month;
  return new Date(year, monthNumber - 1).toLocaleDateString(undefined, {
    month: 'short',
    year: 'numeric',
  });
}

export function engagementDates(start: string, end: string, current: boolean): string {
  const finish = current ? 'Present' : end ? monthLabel(end) : '';
  return [start ? monthLabel(start) : '', finish].filter(Boolean).join(' – ');
}

export function icpExclusions(icp: Icp): string[] {
  return icp.exclusions.map((exclusion) => {
    if (exclusion.kind === 'industry') return exclusion.name;
    if (exclusion.kind === 'geography') return exclusion.geography.value;
    return 'A specific company';
  });
}

// Only web addresses become links, so a saved value can never run script.
export function websiteUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  try {
    const url = new URL(trimmed.includes('://') ? trimmed : `https://${trimmed}`);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch {
    return null;
  }
}

export function websiteLabel(value: string): string {
  return value
    .trim()
    .replace(/^https?:\/\//, '')
    .replace(/\/$/, '');
}
