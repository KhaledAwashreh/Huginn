const HOSTNAME_PATTERN =
  /^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$/;
const SOURCE_HOSTNAME_PATTERN =
  /^(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;

export function companyWebsiteUrl(domain: string | null | undefined): string | null {
  if (!domain || domain !== domain.trim() || !HOSTNAME_PATTERN.test(domain)) return null;
  try {
    const url = new URL(`https://${domain}`);
    return url.hostname.toLowerCase() === domain.toLowerCase() && !url.username && !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}

export function safeSourceUrl(sourceUrl: string | null | undefined): string | null {
  if (
    !sourceUrl ||
    sourceUrl !== sourceUrl.trim() ||
    !/^https?:\/\//i.test(sourceUrl) ||
    sourceUrl.includes('\\') ||
    /[\u0000-\u0020\u007f]/.test(sourceUrl) ||
    !/^https?:\/\/[^/?#]+(?:[/?#]|$)/i.test(sourceUrl)
  )
    return null;
  try {
    const url = new URL(sourceUrl);
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      !url.hostname ||
      (!url.hostname.startsWith('[') &&
        !SOURCE_HOSTNAME_PATTERN.test(url.hostname.replace(/\.$/, ''))) ||
      url.username ||
      url.password ||
      url.pathname.startsWith('//') ||
      /https?:\/\//i.test(url.pathname)
    )
      return null;
    return url.href;
  } catch {
    return null;
  }
}
