import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { components } from '../../src/api/generated/schema';

const recommendation: components['schemas']['RecommendationResponse'] = {
  id: '10000000-0000-0000-0000-000000000001',
  business_id: '20000000-0000-0000-0000-000000000001',
  company_id: '30000000-0000-0000-0000-000000000001',
  status: 'open',
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-02T00:00:00Z',
  current_revision_id: '40000000-0000-0000-0000-000000000001',
  first_presented_at: '2026-11-01T01:00:00Z',
  assessment_presented_at: '2026-11-01T01:00:00Z',
  resolved_at: null,
  resolved_by_user_id: null,
  resolution_reason: null,
  version: 4,
  company: {
    name: 'Northstar Research',
    description: 'Research software for teams working with complex customer data.',
    domain: 'northstar.example',
    country: 'US',
    business_sector: ['Research'],
    company_scale: '11-50',
    company_status: 'active',
  },
  assessment: {
    id: '40000000-0000-0000-0000-000000000001',
    recommendation_id: '10000000-0000-0000-0000-000000000001',
    business_id: '20000000-0000-0000-0000-000000000001',
    company_id: '30000000-0000-0000-0000-000000000001',
    revision_number: 2,
    assessed_at: '2026-11-01T00:00:00Z',
    assessed_by_user_id: '50000000-0000-0000-0000-000000000001',
    strategy_assessments: [
      {
        strategy_id: '60000000-0000-0000-0000-000000000001',
        offering_id: '70000000-0000-0000-0000-000000000001',
        ideal_client_profile_id: '80000000-0000-0000-0000-000000000001',
        strategy_snapshot: { name: 'Research strategy' },
        offering_snapshot: { name: 'Product research' },
        ideal_client_profile_snapshot: { name: 'Research teams' },
        assessment_snapshot: {
          score: 84,
          rationale: 'Their current hiring supports reviewing their research workflow.',
          unknowns: ['The buying role has not been verified.'],
          evidence: [
            {
              observation_id: '90000000-0000-0000-0000-000000000001',
              quote: 'We are adding two data analysts.',
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
        quote: 'We are adding two data analysts.',
        source: 'company website',
        source_url: 'https://northstar.example/careers',
        occurred_at: '2026-10-30T00:00:00Z',
        observed_at: '2026-11-01T00:00:00Z',
      },
    ],
    evidence_observation_ids: ['90000000-0000-0000-0000-000000000001'],
    policy_versions: ['company-fit-v1'],
    evaluation_seed: 'fixture-seed',
  },
  prospect: null,
  selection_state: {
    first_presented_at: '2026-11-01T01:00:00Z',
    cooldown_until: null,
    paused_until: null,
    paused_indefinitely: false,
    rejected: false,
    has_relationship: false,
    pending_delivery: false,
    uncertain_delivery: false,
  },
  selection_blockers: [],
  current_eligibility: 'not_reassessed',
  read_at: '2026-11-14T10:00:00Z',
  evidence_state: 'changed',
  active_blocks: [],
};

const researchStrategy = {
  id: '60000000-0000-0000-0000-000000000001',
  business_id: recommendation.business_id,
  name: 'Research strategy',
  service_offering_id: '70000000-0000-0000-0000-000000000001',
  ideal_client_profile_id: '80000000-0000-0000-0000-000000000001',
  is_active: true,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
};

async function chooseStrategy(page: import('@playwright/test').Page): Promise<void> {
  await page.getByRole('combobox', { name: 'Discovery strategy', exact: true }).click();
  await page.getByRole('option', { name: 'Research strategy', exact: true }).click();
  await expect(page.locator('.p-select-overlay')).toHaveCount(0);
}

test('renders assessment lineage, searches server-side, reports feedback, and saves the exact revision', async ({
  page,
}) => {
  const listQueries: URLSearchParams[] = [];
  const runtimeFaults: string[] = [];
  let saved = false;
  let feedbackRequest: unknown;
  let laterRequest: components['schemas']['LaterRecommendationRequest'] | undefined;
  const offerRequests: string[] = [];
  page.on('pageerror', (error) => {
    runtimeFaults.push(`page error: ${error.message}`);
  });
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText;
    if (failure && failure !== 'net::ERR_ABORTED') runtimeFaults.push(`request failed: ${failure}`);
  });
  page.on('response', (response) => {
    if (response.status() >= 500)
      runtimeFaults.push(`HTTP ${response.status()} ${new URL(response.url()).pathname}`);
  });
  await page.route('**/api/v1/recommendations?*', async (route) => {
    const url = new URL(route.request().url());
    listQueries.push(url.searchParams);
    const search = url.searchParams.get('search')?.toLowerCase() ?? '';
    const status = url.searchParams.get('status');
    const visible =
      !saved &&
      status !== 'converted' &&
      (!search ||
        recommendation.company.name.toLowerCase().includes(search) ||
        recommendation.company.domain.includes(search));
    const body: components['schemas']['PageResponse_RecommendationResponse_'] = {
      items: visible ? [recommendation] : [],
      offset: Number(url.searchParams.get('offset') ?? 0),
      limit: Number(url.searchParams.get('limit') ?? 25),
      has_more: false,
    };
    await route.fulfill({ json: body });
  });
  await page.route('**/api/v1/me/business/recommendation-preferences', (route) =>
    route.fulfill({
      json: {
        business_id: recommendation.business_id,
        repeat_interval_days: 30,
        updated_at: '2026-11-14T10:00:00Z',
      },
    }),
  );
  await page.route('**/api/v1/discovery-strategies?*', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: '60000000-0000-0000-0000-000000000001',
            business_id: recommendation.business_id,
            name: 'Research strategy',
            service_offering_id: '70000000-0000-0000-0000-000000000001',
            ideal_client_profile_id: '80000000-0000-0000-0000-000000000001',
            is_active: true,
            created_at: '2026-11-01T00:00:00Z',
            updated_at: '2026-11-01T00:00:00Z',
          },
        ],
        offset: 0,
        limit: 100,
        has_more: false,
      },
    }),
  );
  await page.route('**/api/v1/suppressions?*', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            company_id: recommendation.company_id,
            company: recommendation.company,
            prospect: null,
            read_at: '2026-11-14T10:00:00Z',
            selection_state: recommendation.selection_state,
            selection_blockers: ['rejection'],
            active_blocks: [
              {
                id: 'd0000000-0000-0000-0000-000000000001',
                business_id: recommendation.business_id,
                company_id: recommendation.company_id,
                kind: 'rejection',
                reason: 'Assessment reported not relevant',
                effective_at: '2026-11-10T10:00:00Z',
                expires_at: null,
                created_at: '2026-11-10T10:00:00Z',
                created_by_user_id: '50000000-0000-0000-0000-000000000001',
                cleared_at: null,
                cleared_by_user_id: null,
                version: 1,
              },
            ],
          },
        ],
        offset: 0,
        limit: 25,
        has_more: false,
      },
    }),
  );
  await page.route('**/api/v1/recommendations/*/later', async (route) => {
    laterRequest = route
      .request()
      .postDataJSON() as components['schemas']['LaterRecommendationRequest'];
    await route.fulfill({
      json: {
        recommendation_id: recommendation.id,
        recommendation_version: recommendation.version + 1,
        pause_choice: laterRequest.pause_choice,
        selected_at: '2026-11-14T10:00:00Z',
        expires_at: '2026-12-14T10:00:00Z',
        repeat_interval_days: 30,
        preference_updated_at: '2026-11-14T10:00:00Z',
        replaced_pause_id: null,
        suppression_block_id: 'e0000000-0000-0000-0000-000000000001',
        remaining_blockers: ['rejection'],
      },
    });
  });
  await page.route('**/api/v1/suppressions/*/reverse-rejection', async (route) => {
    await route.fulfill({
      json: {
        suppression_block_id: 'd0000000-0000-0000-0000-000000000001',
        block_version: 2,
        cleared_at: '2026-11-14T11:00:00Z',
        remaining_blockers: ['cooldown'],
      },
    });
  });
  await page.route(
    /\/api\/v1\/recommendations\/(?:[^/]+\/offer-preparations|offer-preparations\/[^/]+\/confirm)(?:$|\/)/,
    async (route) => {
      offerRequests.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
      await route.fulfill({ status: 404, json: { detail: 'Not used by this workspace' } });
    },
  );
  await page.route('**/api/v1/recommendations/*/feedback', async (route) => {
    feedbackRequest = route.request().postDataJSON();
    const body = feedbackRequest as components['schemas']['RecordRecommendationFeedbackRequest'];
    await route.fulfill({
      json: {
        id: 'a0000000-0000-0000-0000-000000000001',
        business_id: recommendation.business_id,
        recommendation_id: recommendation.id,
        assessment_revision_id: body.assessment_revision_id,
        actor_user_id: '50000000-0000-0000-0000-000000000001',
        feedback: body.feedback,
        recorded_at: '2026-11-14T11:00:00Z',
      },
    });
  });
  await page.route('**/api/v1/recommendations/*/save', async (route) => {
    const body = route
      .request()
      .postDataJSON() as components['schemas']['SaveRecommendationRequest'];
    expect(body.assessment_revision_id).toBe(recommendation.assessment?.id);
    saved = true;
    await route.fulfill({
      status: 201,
      json: {
        recommendation_id: recommendation.id,
        company_id: recommendation.company_id,
        assessment_revision_id: body.assessment_revision_id,
        prospect_id: 'b0000000-0000-0000-0000-000000000001',
        prospect_stage: 'saved',
        prospect_version: 1,
        origin_id: 'c0000000-0000-0000-0000-000000000001',
      },
    });
  });

  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-matches');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  await chooseStrategy(page);
  const firstCard = page.locator('article.recommendation-card');
  await expect(
    firstCard
      .locator('summary')
      .getByText('Research software for teams working with complex customer data.'),
  ).toBeVisible();
  await expect(firstCard.locator('.relevance-score')).toContainText('84/100');
  await expect(
    firstCard.getByRole('heading', { name: 'Company signals', exact: true }),
  ).not.toBeVisible();
  await expect(firstCard.getByLabel('How useful was this assessment?')).not.toBeVisible();
  await firstCard.locator('summary').click();
  await expect(page.getByRole('link', { name: 'Open source', exact: true })).toHaveAttribute(
    'href',
    'https://northstar.example/careers',
  );
  await expect(
    firstCard.getByRole('heading', { name: 'Company signals', exact: true }),
  ).toBeVisible();
  await expect(
    firstCard.getByText('Current source evidence is available and unchanged from this assessment.'),
  ).toHaveCount(0);
  await page.screenshot({ path: 'test-results/compact-scan-expanded-wide.png', fullPage: true });
  await firstCard.locator('summary').click();
  await page.screenshot({ path: 'test-results/compact-scan-collapsed-wide.png', fullPage: true });
  await page.setViewportSize({ width: 375, height: 900 });
  await page.screenshot({ path: 'test-results/compact-scan-collapsed-narrow.png', fullPage: true });
  await firstCard.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(
    firstCard.getByRole('heading', { name: 'Company signals', exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: 'test-results/compact-scan-expanded-narrow.png', fullPage: true });
  const overflow = await page.evaluate(() =>
    Array.from(document.querySelectorAll('*')).flatMap((element) => {
      const box = element.getBoundingClientRect();
      return box.width && (box.right > innerWidth + 1 || box.left < -1)
        ? [{ tag: element.tagName, className: element.className, left: box.left, right: box.right }]
        : [];
    }),
  );
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    JSON.stringify(overflow),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  const search = page.getByRole('searchbox', {
    name: 'Search recommendations by company name or domain',
  });
  await search.fill('northstar.example');
  await expect(
    page.getByRole('heading', { name: 'Northstar Research', exact: true }),
  ).toBeVisible();
  await expect.poll(() => listQueries.at(-1)?.get('search')).toBe('northstar.example');
  await search.fill('no-such-company.example');
  await expect(page.getByText('No recommendations match this view yet.')).toBeVisible();
  await search.fill('northstar');
  await expect(
    page.getByRole('heading', { name: 'Northstar Research', exact: true }),
  ).toBeVisible();

  await page.getByRole('button', { name: 'Not relevant' }).click();
  await page.getByLabel('How useful was this assessment?').selectOption('not_useful');
  await page.getByLabel('Outcome').selectOption('not_relevant');
  await page.getByLabel('Correction').fill('The original hiring evidence is no longer current.');
  await page.getByRole('button', { name: 'Submit assessment report' }).click();
  await expect(
    page.getByText(
      'Feedback recorded. This report does not change your recommendation or its ranking.',
      { exact: true },
    ),
  ).toBeVisible();
  expect(feedbackRequest).toMatchObject({ assessment_revision_id: recommendation.assessment?.id });
  await page.getByLabel('Reason (optional)').fill('Not a fit right now.');
  await page.getByLabel('Mute days').fill('45');
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Muted until' })).toContainText(
    'Muted until',
  );
  expect(laterRequest).toMatchObject({
    assessment_revision_id: recommendation.assessment?.id,
    expected_pause_id: null,
    expected_pause_version: null,
    expected_preference_updated_at: '2026-11-14T10:00:00Z',
    expected_repeat_interval_days: 30,
    expected_recommendation_version: recommendation.version,
    pause_choice: 'd45',
    reason: 'Not a fit right now.',
  });

  await page.getByRole('button', { name: 'Manage suppressions' }).click();
  await expect(page.getByRole('heading', { name: 'Manage suppressions' })).toBeVisible();
  await expect(page.getByText(/Clearing one does not clear others/)).toBeVisible();
  await page.getByRole('button', { name: 'Reverse rejection' }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByText(/Rejection reversed\. Independent blocks remain unchanged/),
  ).toBeVisible();

  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 375, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: 'test-results/recommendations-narrow.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: 'test-results/recommendations-wide.png', fullPage: true });

  await page.getByRole('button', { name: 'Save as prospect' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Saved as a prospect.' })).toBeVisible();
  await expect(page.getByText('No recommendations match this view yet.')).toBeVisible();
  expect(runtimeFaults).toEqual([]);
  expect(offerRequests).toEqual([]);
});

test('confirms first presentation only after the exact assessment revision is rendered', async ({
  page,
}) => {
  const firstOffer: components['schemas']['RecommendationResponse'] = {
    ...recommendation,
    first_presented_at: null,
    assessment_presented_at: null,
    evidence_state: 'current',
    selection_state: { ...recommendation.selection_state, first_presented_at: null },
  };
  const revisionId = firstOffer.assessment?.id;
  if (!revisionId) throw new Error('The first-offer fixture needs an assessment revision.');
  const order: string[] = [];
  let prepareBody: components['schemas']['PrepareRecommendationOfferRequest'] | undefined;
  let confirmationVisible = false;
  page.on('pageerror', (error) => order.push(`pageerror:${error.message}`));
  await page.route('**/api/v1/recommendations?*', (route) =>
    route.fulfill({
      json: {
        items: [firstOffer],
        offset: 0,
        limit: 25,
        has_more: false,
      } satisfies components['schemas']['PageResponse_RecommendationResponse_'],
    }),
  );
  await page.route('**/api/v1/me/business/recommendation-preferences', (route) =>
    route.fulfill({
      json: {
        business_id: firstOffer.business_id,
        repeat_interval_days: 30,
        updated_at: '2026-11-14T10:00:00Z',
      },
    }),
  );
  await page.route('**/api/v1/discovery-strategies?*', (route) =>
    route.fulfill({ json: { items: [researchStrategy], offset: 0, limit: 100, has_more: false } }),
  );
  await page.route('**/api/v1/suppressions?*', (route) =>
    route.fulfill({ json: { items: [], offset: 0, limit: 25, has_more: false } }),
  );
  await page.route('**/api/v1/recommendations/*/offer-preparations', async (route) => {
    prepareBody = route
      .request()
      .postDataJSON() as components['schemas']['PrepareRecommendationOfferRequest'];
    order.push('prepare');
    await route.fulfill({
      json: {
        offer_cycle_id: 'a0000000-0000-0000-0000-000000000001',
        recommendation_id: firstOffer.id,
        assessment_revision_id: revisionId,
        status: 'preparing',
        claim_token: 'short-lived-test-claim',
        lease_expires_at: '2026-11-15T12:05:00Z',
        presented_at: null,
      } satisfies components['schemas']['PreparedRecommendationOfferResponse'],
    });
  });
  await page.route('**/api/v1/recommendations/offer-preparations/*/confirm', async (route) => {
    const body = route
      .request()
      .postDataJSON() as components['schemas']['ConfirmRecommendationOfferRequest'];
    expect(body.claim_token).toBe('short-lived-test-claim');
    confirmationVisible = await page
      .locator(`[data-assessment-revision-id="${revisionId}"]`)
      .isVisible();
    order.push('confirm');
    await route.fulfill({
      json: {
        offer_cycle_id: 'a0000000-0000-0000-0000-000000000001',
        recommendation_id: firstOffer.id,
        assessment_revision_id: revisionId,
        presented_at: '2026-11-15T11:30:00Z',
        cooldown_expires_at: '2026-12-15T11:30:00Z',
      } satisfies components['schemas']['ConfirmedRecommendationOfferResponse'],
    });
  });

  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-matches');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  await chooseStrategy(page);
  await expect(
    page
      .locator('article.recommendation-card summary')
      .getByText('Research software for teams working with complex customer data.'),
  ).toBeVisible();
  await expect(page.locator('article.recommendation-card details')).not.toHaveAttribute('open');
  const renderedAssessment = page.locator(`[data-assessment-revision-id="${revisionId}"]`);
  await expect(renderedAssessment).toHaveAttribute('data-assessment-revision-id', revisionId);
  await expect.poll(() => order[0]).toBe('prepare');
  await renderedAssessment.scrollIntoViewIfNeeded();
  await expect.poll(() => order).toEqual(['prepare', 'confirm']);
  expect(prepareBody).toMatchObject({
    assessment_revision_id: firstOffer.assessment?.id,
    request_key: expect.any(String),
  });
  expect(confirmationVisible).toBe(true);
  expect(order).toEqual(['prepare', 'confirm']);
});

test('keeps an email assessment historical while confirming an unrelated repeat across reload', async ({
  page,
}) => {
  const oldRevisionId = '40000000-0000-0000-0000-000000000009';
  const oldAssessment = recommendation.assessment;
  if (!oldAssessment) throw new Error('The email fixture needs an assessment revision.');
  const linked: components['schemas']['RecommendationResponse'] = {
    ...recommendation,
    first_presented_at: null,
    assessment_presented_at: null,
    current_revision_id: '40000000-0000-0000-0000-000000000010',
    assessment: {
      ...oldAssessment,
      id: oldRevisionId,
      revision_number: 1,
    },
  };
  const detailQueries: URLSearchParams[] = [];
  const offers: string[] = [];
  const saves: { recommendationId: string; revisionId: string }[] = [];
  const expectedRepeatPresentedAt = '2026-11-15T11:30:00Z';
  let showUnrelated = false;
  let repeatPresentedAt: string | null = null;
  const repeat: components['schemas']['RecommendationResponse'] = {
    ...recommendation,
    id: '10000000-0000-0000-0000-000000000002',
    company_id: '30000000-0000-0000-0000-000000000002',
    company: { ...recommendation.company, name: 'Unrelated Research', domain: 'unrelated.example' },
    current_revision_id: '40000000-0000-0000-0000-000000000002',
    assessment_presented_at: null,
    evidence_state: 'current',
    assessment: {
      ...oldAssessment,
      id: '40000000-0000-0000-0000-000000000002',
      recommendation_id: '10000000-0000-0000-0000-000000000002',
      company_id: '30000000-0000-0000-0000-000000000002',
    },
  };
  await page.route('**/api/v1/recommendations?*', (route) =>
    route.fulfill({
      json: {
        items: showUnrelated ? [{ ...repeat, assessment_presented_at: repeatPresentedAt }] : [],
        offset: 0,
        limit: 25,
        has_more: false,
      } satisfies components['schemas']['PageResponse_RecommendationResponse_'],
    }),
  );
  await page.route(/\/api\/v1\/recommendations\/[^/?]+(?:\?.*)?$/, async (route) => {
    const url = new URL(route.request().url());
    detailQueries.push(url.searchParams);
    await route.fulfill({ json: linked });
  });
  await page.route('**/api/v1/me/business/recommendation-preferences', (route) =>
    route.fulfill({
      json: {
        business_id: linked.business_id,
        repeat_interval_days: 30,
        updated_at: '2026-11-14T10:00:00Z',
      },
    }),
  );
  await page.route('**/api/v1/suppressions?*', (route) =>
    route.fulfill({ json: { items: [], offset: 0, limit: 25, has_more: false } }),
  );
  await page.route('**/api/v1/discovery-strategies?*', (route) =>
    route.fulfill({ json: { items: [researchStrategy], offset: 0, limit: 100, has_more: false } }),
  );
  await page.route('**/api/v1/recommendations/*/offer-preparations', async (route) => {
    offers.push(new URL(route.request().url()).pathname);
    expect(route.request().postDataJSON()).toMatchObject({
      assessment_revision_id: repeat.assessment?.id,
    });
    await route.fulfill({
      json: {
        recommendation_id: repeat.id,
        assessment_revision_id: repeat.assessment?.id,
        offer_cycle_id: 'a0000000-0000-0000-0000-000000000002',
        status: 'preparing',
        claim_token: 'unrelated-repeat-claim',
        presented_at: null,
        lease_expires_at: '2026-11-15T12:05:00Z',
      },
    });
  });
  await page.route('**/api/v1/recommendations/offer-preparations/*/confirm', async (route) => {
    offers.push(new URL(route.request().url()).pathname);
    expect(route.request().postDataJSON()).toEqual({ claim_token: 'unrelated-repeat-claim' });
    expect(
      await page.locator(`[data-assessment-revision-id="${repeat.assessment?.id}"]`).isVisible(),
    ).toBe(true);
    await route.fulfill({
      json: {
        recommendation_id: repeat.id,
        assessment_revision_id: repeat.assessment?.id,
        offer_cycle_id: 'a0000000-0000-0000-0000-000000000002',
        presented_at: expectedRepeatPresentedAt,
        cooldown_expires_at: '2026-12-15T11:30:00Z',
      },
    });
    repeatPresentedAt = expectedRepeatPresentedAt;
  });
  await page.route('**/api/v1/recommendations/*/save', async (route) => {
    const recommendationId = new URL(route.request().url()).pathname.split('/').at(-2);
    if (!recommendationId) throw new Error('Save must identify a recommendation');
    saves.push({
      recommendationId,
      revisionId: route.request().postDataJSON().assessment_revision_id,
    });
    await route.fulfill({ json: { prospect_id: 'b0000000-0000-0000-0000-000000000002' } });
  });

  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-matches');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  await chooseStrategy(page);
  showUnrelated = true;
  await page.goto(
    `/recommendations?recommendation_id=${linked.id}&assessment_revision_id=${oldRevisionId}`,
  );
  await chooseStrategy(page);
  await expect(page.getByRole('heading', { name: 'Recommendation from your email' })).toBeVisible();
  const historicalCard = page.getByRole('region', { name: 'Recommendation from your email' });
  await expect(
    historicalCard.locator(`[data-assessment-revision-id="${oldRevisionId}"]`),
  ).toBeVisible();
  await historicalCard.locator('summary').click();
  await expect(
    historicalCard.getByText('We are adding two data analysts.', { exact: true }),
  ).toBeVisible();
  await expect.poll(() => detailQueries.at(-1)?.get('assessment_revision_id')).toBe(oldRevisionId);
  const card = page.locator('article.recommendation-card');
  await card.scrollIntoViewIfNeeded();
  const assessment = card.locator(`[data-assessment-revision-id="${repeat.assessment?.id}"]`);
  await expect(assessment).toBeVisible();
  await assessment.scrollIntoViewIfNeeded();
  await expect
    .poll(() => offers)
    .toEqual([
      `/api/v1/recommendations/${repeat.id}/offer-preparations`,
      '/api/v1/recommendations/offer-preparations/a0000000-0000-0000-0000-000000000002/confirm',
    ]);
  await expect.poll(() => repeatPresentedAt).toBe(expectedRepeatPresentedAt);
  await page.reload();
  await chooseStrategy(page);
  await expect(card.getByText('Unrelated Research', { exact: true })).toBeVisible();
  await card.getByRole('button', { name: 'Save as prospect' }).click();
  const email = page.getByRole('region', { name: 'Recommendation from your email' });
  await email.getByRole('button', { name: 'Save as prospect' }).click();
  await expect
    .poll(() => saves)
    .toEqual([
      { recommendationId: repeat.id, revisionId: repeat.assessment?.id },
      { recommendationId: linked.id, revisionId: oldRevisionId },
    ]);
  expect(offers).toHaveLength(2);
});

test('searches recommendations beyond page one and resets pagination offset', async ({ page }) => {
  const rows = Array.from({ length: 26 }, (_, index) => {
    const number = String(index + 1).padStart(2, '0');
    return {
      ...recommendation,
      id: `10000000-0000-0000-0000-${number.padStart(12, '0')}`,
      company_id: `30000000-0000-0000-0000-${number.padStart(12, '0')}`,
      current_revision_id: null,
      assessment: null,
      company: {
        ...recommendation.company,
        name: `Recommendation ${number}`,
        domain: `recommendation-${number}.example`,
      },
    } satisfies components['schemas']['RecommendationResponse'];
  });
  const queries: URLSearchParams[] = [];
  await page.route('**/api/v1/recommendations?*', async (route) => {
    const url = new URL(route.request().url());
    queries.push(url.searchParams);
    const search = url.searchParams.get('search')?.toLowerCase() ?? '';
    const offset = Number(url.searchParams.get('offset') ?? 0);
    const limit = Number(url.searchParams.get('limit') ?? 25);
    const filtered = rows.filter(
      (item) =>
        item.company.name.toLowerCase().includes(search) ||
        item.company.domain.toLowerCase().includes(search),
    );
    const items = filtered.slice(offset, offset + limit);
    await route.fulfill({
      json: {
        items,
        offset,
        limit,
        has_more: offset + items.length < filtered.length,
      } satisfies components['schemas']['PageResponse_RecommendationResponse_'],
    });
  });
  await page.route('**/api/v1/me/business/recommendation-preferences', (route) =>
    route.fulfill({
      json: {
        business_id: recommendation.business_id,
        repeat_interval_days: 30,
        updated_at: '2026-11-14T10:00:00Z',
      },
    }),
  );
  await page.route('**/api/v1/discovery-strategies?*', (route) =>
    route.fulfill({ json: { items: [researchStrategy], offset: 0, limit: 100, has_more: false } }),
  );
  await page.route('**/api/v1/suppressions?*', (route) =>
    route.fulfill({ json: { items: [], offset: 0, limit: 25, has_more: false } }),
  );

  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-matches');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  await chooseStrategy(page);
  await expect(page.getByText('Recommendation 01', { exact: true })).toBeVisible();
  await expect(page.getByText('Showing 1–25')).toBeVisible();
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByText('Recommendation 26', { exact: true })).toBeVisible();
  await expect(page.getByText('Showing 26–26')).toBeVisible();
  await page
    .getByRole('searchbox', { name: 'Search recommendations by company name or domain' })
    .fill('Recommendation 26');
  await expect(page.getByText('Recommendation 26', { exact: true })).toBeVisible();
  await expect(page.getByText('Showing 1–1')).toBeVisible();
  await expect.poll(() => queries.at(-1)?.get('search')).toBe('Recommendation 26');
  await expect.poll(() => queries.at(-1)?.get('offset')).toBe('0');
});
