import { describe, expect, it } from 'vitest';
import { companyWebsiteUrl, safeSourceUrl } from '@/features/matches/lib/externalCompanyUrl';

describe('external match context URLs', () => {
  it('constructs HTTPS only for a hostname and accepts explicit HTTP(S) signal links', () => {
    expect(companyWebsiteUrl('example.com')).toBe('https://example.com/');
    expect(safeSourceUrl('https://news.example/story?id=1')).toBe(
      'https://news.example/story?id=1',
    );
    expect(safeSourceUrl('http://news.example/story')).toBe('http://news.example/story');
    expect(safeSourceUrl('http://localhost/story')).toBe('http://localhost/story');
    expect(safeSourceUrl('https://127.0.0.1/story')).toBe('https://127.0.0.1/story');
    expect(safeSourceUrl('https://[::1]/story')).toBe('https://[::1]/story');
  });

  it.each([
    'https://example.com',
    '//example.com',
    'javascript:alert(1)',
    'https://user:pass@example.com/story',
    'https://https://example.com',
    'https://example.com/https://nested.example',
    'https://example.com\\\\evil.test',
    'https:///example.com',
    'https://example.com:bad',
    'https://example.com\n.evil.test',
    'example.com/path',
    'bad host.example',
    '-bad.example',
  ])('keeps unsafe company domain %s as plain text', (value) => {
    expect(companyWebsiteUrl(value)).toBeNull();
  });

  it.each([
    '//example.com',
    'javascript:alert(1)',
    'https://user:pass@example.com/story',
    'https://https://example.com',
    'https://example.com/https://nested.example',
    'https://example.com\\\\evil.test',
    'example.com/path',
    'https://-bad.example/',
    'https://bad-.example/',
    'https://bad..example/',
  ])('keeps unsafe signal URL %s as plain text', (value) => {
    expect(safeSourceUrl(value)).toBeNull();
  });
});
