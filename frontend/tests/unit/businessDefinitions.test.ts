import { afterEach, expect, it, vi } from 'vitest';
import { configureApiClient } from '../../src/api/client';
import { listServiceOfferings } from '../../src/features/configuration/offerings/api/listServiceOfferings';
import { serializeServiceOfferingPatch } from '../../src/features/configuration/offerings/forms/serializeServiceOfferingPatch';
import { serializeIdealClientProfilePatch } from '../../src/features/configuration/ideal-client-profiles/forms/serializeIdealClientProfilePatch';
import type { ServiceOfferingDraft } from '../../src/features/configuration/offerings/forms/serviceOfferingDraft';
import type { IdealClientProfileDraft } from '../../src/features/configuration/ideal-client-profiles/forms/idealClientProfileDraft';

afterEach(() => {
  configureApiClient({ getCsrfToken: () => 'csrf' });
  vi.unstubAllGlobals();
});

it('serializes only changed offering fields and keeps required values', () => {
  const baseline: ServiceOfferingDraft = { name: 'Advisory', description: 'Launch support' };
  expect(
    serializeServiceOfferingPatch(baseline, { ...baseline, description: 'GTM support' }),
  ).toEqual({
    description: 'GTM support',
  });
  expect(serializeServiceOfferingPatch(baseline, baseline)).toBeNull();
});

it('preserves ICP array order and explicit empty array clears', () => {
  const baseline: IdealClientProfileDraft = {
    name: 'B2B SaaS',
    industries: [{ name: 'SaaS' }, { name: 'Fintech' }],
    company_sizes: [{ band: '11-100' }],
    geographies: [{ kind: 'region', value: 'Nordics' }],
    exclusions: [
      { kind: 'industry', name: 'Agency' },
      { kind: 'company', company_id: '27cc0e60-1d65-4d7e-aaed-f122181ba157' },
    ],
  };
  expect(serializeIdealClientProfilePatch(baseline, { ...baseline, industries: [] })).toEqual({
    industries: [],
  });
  expect(
    serializeIdealClientProfilePatch(baseline, {
      ...baseline,
      industries: [...baseline.industries].reverse(),
    }),
  ).toEqual({
    industries: [{ name: 'Fintech' }, { name: 'SaaS' }],
  });
  expect(serializeIdealClientProfilePatch(baseline, baseline)).toBeNull();
});

it('bounds offerings requests to 100 and includes the supplied offset and signal', async () => {
  const fetch = vi.fn<typeof globalThis.fetch>(() =>
    Promise.resolve(
      Response.json({ items: [], limit: 100, offset: 200, has_more: false }, { status: 200 }),
    ),
  );
  vi.stubGlobal('fetch', fetch);
  const controller = new AbortController();
  await listServiceOfferings(200, 500, controller.signal);
  expect(fetch.mock.calls[0]?.[0]).toBe('/api/v1/offerings?limit=100&offset=200');
  expect((fetch.mock.calls[0]?.[1] as RequestInit | undefined)?.signal).toBe(controller.signal);
});
