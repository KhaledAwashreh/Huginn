export function validateReturnPath(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return '/';
  let decoded: string;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return '/';
  }
  if (decoded.startsWith('//') || decoded.includes('\\') || /[\u0000-\u001f\u007f]/.test(decoded))
    return '/';
  const parsed = new URL(decoded, 'https://huginn.invalid');
  if (parsed.origin !== 'https://huginn.invalid' || parsed.pathname === '/login') return '/';
  return value;
}
