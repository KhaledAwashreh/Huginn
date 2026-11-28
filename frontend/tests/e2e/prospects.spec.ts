import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { components } from '../../src/api/generated/schema';

type Prospect = components['schemas']['ProspectResponse'];
type Activity = components['schemas']['ProspectActivityResponse'];

function activity(overrides: Partial<Activity> = {}): Activity {
  return {
    id: 'a0000000-0000-0000-0000-000000000001',
    business_id: 'b0000000-0000-0000-0000-000000000001',
    prospect_id: 'c0000000-0000-0000-0000-000000000001',
    actor_user_id: 'd0000000-0000-0000-0000-000000000001',
    kind: 'stage_changed',
    occurred_at: '2026-11-01T10:00:00Z',
    effective_occurred_at: '2026-11-01T10:00:00Z',
    recorded_at: '2026-11-01T10:01:00Z',
    payload: { prior_stage: 'contacted', new_stage: 'in_conversation', reason: null },
    correction_of_id: null,
    correction_head_id: null,
    correction_sequence: 0,
    ...overrides,
  };
}

function prospect(): Prospect {
  return {
    id: 'c0000000-0000-0000-0000-000000000001',
    business_id: 'b0000000-0000-0000-0000-000000000001',
    company_id: 'e0000000-0000-0000-0000-000000000001',
    company: {
      name: 'Northstar Research',
      domain: 'northstar.example',
      country: 'US',
      business_sector: ['Research'],
      company_scale: '11-50',
      company_status: 'active',
    },
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
    stage: 'in_conversation',
    last_active_stage: null,
    notes: 'Review the research team’s workflow requirements.',
    follow_up_at: null,
    version: 4,
    current_source_context: { signals: [], has_more: false, evidence_state: 'unavailable' },
    activities: [activity()],
    origins: [
      {
        id: 'f0000000-0000-0000-0000-000000000001',
        business_id: 'b0000000-0000-0000-0000-000000000001',
        prospect_id: 'c0000000-0000-0000-0000-000000000001',
        company_id: 'e0000000-0000-0000-0000-000000000001',
        recommendation_id: '10000000-0000-0000-0000-000000000001',
        assessment_revision_id: '40000000-0000-0000-0000-000000000001',
        recommendation_status: 'converted',
        recommendation_version: 5,
        created_by_user_id: 'd0000000-0000-0000-0000-000000000001',
        created_at: '2026-11-01T10:00:00Z',
        assessment: {
          id: '40000000-0000-0000-0000-000000000001',
          recommendation_id: '10000000-0000-0000-0000-000000000001',
          business_id: 'b0000000-0000-0000-0000-000000000001',
          company_id: 'e0000000-0000-0000-0000-000000000001',
          revision_number: 2,
          assessed_at: '2026-10-30T10:00:00Z',
          assessed_by_user_id: 'd0000000-0000-0000-0000-000000000001',
          strategy_assessments: [
            {
              strategy_id: '60000000-0000-0000-0000-000000000001',
              offering_id: '70000000-0000-0000-0000-000000000001',
              ideal_client_profile_id: '80000000-0000-0000-0000-000000000001',
              strategy_snapshot: { name: 'Research strategy' },
              offering_snapshot: { name: 'Product research' },
              ideal_client_profile_snapshot: { name: 'Research teams' },
              assessment_snapshot: {
                rationale: 'Recent hiring suggests a research workflow review.',
                unknowns: ['The buying role has not been verified.'],
                evidence: [
                  {
                    observation_id: '90000000-0000-0000-0000-000000000001',
                    quote: 'We are adding two analysts.',
                  },
                ],
                company_facts: { country: 'US' },
              },
            },
          ],
          professional_profile_snapshot: { headline: 'Research consulting' },
          evidence_snapshots: [
            {
              observation_id: '90000000-0000-0000-0000-000000000001',
              quote: 'We are adding two analysts.',
              source: 'company website',
              source_url: 'https://northstar.example/careers',
              occurred_at: '2026-10-28T10:00:00Z',
              observed_at: '2026-10-30T10:00:00Z',
            },
          ],
          evidence_observation_ids: ['90000000-0000-0000-0000-000000000001'],
          policy_versions: ['company-fit-v1'],
          evaluation_seed: 'prospect-e2e-fixture',
        },
      },
    ],
  };
}

test('searches, updates and reviews a prospect without inferring communication or stage changes', async ({
  page,
}) => {
  const current = prospect();
  const commands: { path: string; body: unknown }[] = [];
  const listQueries: URLSearchParams[] = [];
  const externalActions: string[] = [];
  const runtimeFaults: string[] = [];
  page.on('pageerror', (error) => runtimeFaults.push(`page error: ${error.message}`));
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText;
    if (failure && failure !== 'net::ERR_ABORTED') runtimeFaults.push(`request failed: ${failure}`);
  });
  page.on('response', (response) => {
    if (response.status() >= 500)
      runtimeFaults.push(`HTTP ${response.status()} ${new URL(response.url()).pathname}`);
  });
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (
      /\/(?:outreach|emails?|notifications)(?:\/|$)/i.test(path) ||
      path.includes('offer-preparations')
    )
      externalActions.push(`${request.method()} ${path}`);
  });

  await page.route('**/api/v1/prospects?*', async (route) => {
    const url = new URL(route.request().url());
    listQueries.push(url.searchParams);
    const search = url.searchParams.get('search')?.toLowerCase() ?? '';
    const stage = url.searchParams.get('stage');
    const visible =
      (!search ||
        current.company.name.toLowerCase().includes(search) ||
        current.company.domain.includes(search)) &&
      (!stage || current.stage === stage);
    const body: components['schemas']['PageResponse_ProspectResponse_'] = {
      items: visible ? [current] : [],
      offset: Number(url.searchParams.get('offset') ?? 0),
      limit: Number(url.searchParams.get('limit') ?? 25),
      has_more: false,
    };
    await route.fulfill({ json: body });
  });
  await page.route('**/api/v1/prospects/*', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path.endsWith(current.id)) {
      await route.fulfill({ json: current });
      return;
    }
    await route.fallback();
  });
  await page.route('**/api/v1/prospects/*/*', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const body = request.postDataJSON() as Record<string, unknown>;
    commands.push({ path, body });
    if (path.endsWith('/stage')) {
      current.stage = body.target_stage as Prospect['stage'];
      current.version += 1;
      current.updated_at = '2026-11-15T11:00:00Z';
      current.activities = [
        ...(current.activities ?? []),
        activity({
          id: `b0000000-0000-0000-0000-00000000000${commands.length}`,
          kind: 'stage_changed',
          occurred_at: body.occurred_at as string,
          effective_occurred_at: body.occurred_at as string,
          recorded_at: '2026-11-15T11:00:01Z',
          payload: {
            prior_stage: 'in_conversation',
            new_stage: body.target_stage,
            reason: body.reason,
          },
        }),
      ];
    } else if (path.endsWith('/proposal-drafts')) {
      current.activities = [
        ...(current.activities ?? []),
        activity({
          id: `b0000000-0000-0000-0000-00000000000${commands.length}`,
          kind: 'proposal_drafted',
          occurred_at: body.occurred_at as string,
          effective_occurred_at: body.occurred_at as string,
          recorded_at: '2026-11-15T11:10:01Z',
          payload: { summary: body.summary },
        }),
      ];
    } else if (path.endsWith('/notes')) {
      current.notes = body.replacement_notes as string;
      current.version += 1;
    } else if (path.endsWith('/follow-up')) {
      current.follow_up_at = body.follow_up_at as string;
      current.version += 1;
    } else if (path.endsWith('/clear-follow-up')) {
      current.follow_up_at = null;
      current.version += 1;
    }
    await route.fulfill({
      json: {
        prospect: {
          id: current.id,
          business_id: current.business_id,
          company_id: current.company_id,
          stage: current.stage,
          last_active_stage: current.last_active_stage,
          notes: current.notes,
          follow_up_at: current.follow_up_at,
          created_at: current.created_at,
          updated_at: current.updated_at,
          version: current.version,
        },
        activity: activity({ kind: 'stage_changed' }),
      } satisfies components['schemas']['ProspectCommandResponse'],
    });
  });

  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill('browser-matches@example.test');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  await page.goto(`/prospects?prospect_id=${current.id}`);
  await expect(page.getByRole('heading', { name: 'Prospects', exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Northstar Research', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Why this prospect was saved')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open source', exact: true })).toHaveAttribute(
    'href',
    'https://northstar.example/careers',
  );

  const search = page.getByRole('searchbox', {
    name: 'Search prospects by company name or domain',
  });
  await search.fill('northstar.example');
  await expect.poll(() => listQueries.at(-1)?.get('search')).toBe('northstar.example');
  await search.fill('no-such-company.example');
  await expect(page.getByText('No prospects match this view.')).toBeVisible();
  await expect.poll(() => listQueries.at(-1)?.get('search')).toBe('no-such-company.example');
  await search.fill('northstar');
  await expect(page.getByRole('button', { name: 'Move to proposal sent' })).toBeVisible();

  const nextStage = page.getByRole('button', { name: 'Move to proposal sent' });
  await nextStage.focus();
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Save stage change' }).click();
  await expect(page.getByText('Current stage: proposal sent')).toBeVisible();

  await page.getByRole('button', { name: 'Record proposal draft' }).click();
  await page.getByLabel('Draft summary').fill('Outline research deliverables and milestones.');
  await page.getByRole('button', { name: 'Record proposal draft' }).last().click();
  await expect(page.getByText('Outline research deliverables and milestones.')).toBeVisible();
  await expect(page.getByText('Current stage: proposal sent')).toBeVisible();

  await page.getByRole('button', { name: 'Edit notes' }).click();
  await page.getByLabel('Prospect notes').fill('');
  await page.getByRole('button', { name: 'Save notes' }).click();
  await expect(page.getByText('No notes yet.')).toBeVisible();

  await page.getByRole('button', { name: 'Set reminder' }).click();
  await page.getByLabel('Reminder date and time').fill('2026-11-20T09:00');
  await page.getByRole('button', { name: 'Save reminder' }).click();
  await expect(page.getByText(/Remind me/)).toBeVisible();
  expect(commands.map(({ path }) => path)).toEqual([
    `/api/v1/prospects/${current.id}/stage`,
    `/api/v1/prospects/${current.id}/proposal-drafts`,
    `/api/v1/prospects/${current.id}/notes`,
    `/api/v1/prospects/${current.id}/follow-up`,
  ]);

  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  const correctionButtons = page.getByRole('button', { name: 'Correct occurrence time' });
  await expect(correctionButtons).toHaveCount(3);
  await expect(correctionButtons.first()).toBeVisible();
  await expect(correctionButtons).toHaveText([
    'Correct occurrence time',
    'Correct occurrence time',
    'Correct occurrence time',
  ]);

  const prepareScreenshot = async () => {
    await page.evaluate(async () => {
      await document.fonts.ready;
      (document.activeElement as HTMLElement | null)?.blur();
      window.scrollTo(0, 0);
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    });
  };
  await page.setViewportSize({ width: 375, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await prepareScreenshot();
  await page.screenshot({ path: 'test-results/prospects-narrow.png' });
  await page.locator('.detail-panel').scrollIntoViewIfNeeded();
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
  await page.screenshot({ path: 'test-results/prospects-narrow-detail.png' });
  await page.setViewportSize({ width: 1280, height: 900 });
  await prepareScreenshot();
  await page.screenshot({ path: 'test-results/prospects-wide.png' });
  expect(runtimeFaults).toEqual([]);
  expect(externalActions).toEqual([]);
});

test('search reaches prospects beyond the first page and resets the server offset', async ({
  page,
}) => {
  const records = Array.from({ length: 26 }, (_, index) => {
    const base = prospect();
    return {
      ...base,
      id: `c0000000-0000-0000-0000-${String(index + 1).padStart(12, '0')}`,
      company_id: `e0000000-0000-0000-0000-${String(index + 1).padStart(12, '0')}`,
      company: {
        ...base.company,
        name: `Prospect ${String(index + 1).padStart(2, '0')}`,
        domain: `prospect-${String(index + 1).padStart(2, '0')}.example`,
      },
    };
  });
  const queries: URLSearchParams[] = [];
  await page.route('**/api/v1/prospects?*', async (route) => {
    const url = new URL(route.request().url());
    queries.push(url.searchParams);
    const search = url.searchParams.get('search')?.toLowerCase() ?? '';
    const offset = Number(url.searchParams.get('offset') ?? 0);
    const limit = Number(url.searchParams.get('limit') ?? 25);
    const filtered = records.filter(
      (item) =>
        item.company.name.toLowerCase().includes(search) ||
        item.company.domain.toLowerCase().includes(search),
    );
    const items = filtered.slice(offset, offset + limit);
    const body: components['schemas']['PageResponse_ProspectResponse_'] = {
      items,
      offset,
      limit,
      has_more: offset + items.length < filtered.length,
    };
    await route.fulfill({ json: body });
  });

  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill('browser-matches@example.test');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  await page.goto('/prospects');
  await expect(page.getByRole('button', { name: 'Open prospect Prospect 01' })).toBeVisible();
  await expect(page.getByText('Showing 1–25')).toBeVisible();
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByRole('button', { name: 'Open prospect Prospect 26' })).toBeVisible();
  await expect(page.getByText('Showing 26–26')).toBeVisible();
  await page
    .getByRole('searchbox', { name: 'Search prospects by company name or domain' })
    .fill('Prospect 26');
  await expect(page.getByRole('button', { name: 'Open prospect Prospect 26' })).toBeVisible();
  await expect(page.getByText('Showing 1–1')).toBeVisible();
  await expect.poll(() => queries.at(-1)?.get('search')).toBe('Prospect 26');
  await expect.poll(() => queries.at(-1)?.get('offset')).toBe('0');
});
