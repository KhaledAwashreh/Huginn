import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('weekly selection has seven saved entries, strategy associations and no generation action', async ({
  page,
}) => {
  const strategy = '00000000-0000-0000-0000-000000000111';
  const batchId = '00000000-0000-0000-0000-000000000222';
  const batch = {
    id: batchId,
    kind: 'weekly',
    strategy_id: strategy,
    created_at: '2026-10-28T12:00:00Z',
    algorithm_version: 'research-ranking-v1',
    assessment_method: 'topic-overlap-v1',
    candidate_count: 15,
    retrieval_limit: 200,
    items: Array.from({ length: 7 }, (_, index) => ({
      id: `weekly-${index}`,
      company: {
        id: `company-${index}`,
        name: `Weekly company ${index + 1}`,
        domain: 'example.test',
        country: index ? 'UK' : null,
        business_sector: ['Fintech'],
        company_scale: '11-100',
      },
      score: 37,
      confidence: 'low',
      selection_type: 'exploitation',
      rationale: 'A dated source supports reviewing their data engineering activity.',
      unknowns: index
        ? ['Buyer need is unconfirmed.']
        : ['ICP country is unverified: source information is missing.'],
      icp_fit: { country: index ? 'match' : 'unknown', industry: 'match', size: 'match' },
      strategies: [{ id: strategy, name: 'Data strategy', offering: 'Data engineering' }],
      breakdown: { service_fit: 12, business_context: 0, company_preferences: 10, timing: 15 },
      evidence: [
        {
          quote: 'We are building a data platform.',
          source_url: 'https://example.test/source',
          occurred_at: '2026-10-20T00:00:00Z',
          observed_at: '2026-10-28T00:00:00Z',
        },
      ],
    })),
  };
  await page.route('**/api/v1/recommendations/weekly?*', (route) =>
    route.fulfill({ json: [batch] }),
  );
  await page.route(`**/api/v1/recommendations/${batchId}`, (route) =>
    route.fulfill({ json: batch }),
  );
  await page.route(`**/api/v1/recommendations/${batchId}/feedback`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-matches');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
  await page.getByRole('link', { name: 'Weekly Matches', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Weekly Matches', exact: true })).toBeVisible();
  await expect(page.locator('.recommendation-row')).toHaveCount(7);
  await expect(page.getByRole('button', { name: /Generate/ })).toHaveCount(0);
  await expect(
    page.getByText('Some ICP information is unverified.', { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Data strategy', exact: true })).toHaveCount(7);
  await page.locator('.recommendation-row').first().locator('summary').click();
  await expect(
    page.getByText('ICP country is unverified: source information is missing.'),
  ).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 375, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/weekly-matches-mobile.png', fullPage: true });
  await page.reload();
  await expect(page.locator('.recommendation-row')).toHaveCount(7);
  await page.route('**/api/v1/discovery-strategies?*', (route) =>
    route.fulfill({ json: { items: [{ id: strategy, name: 'Data strategy' }], has_more: false } }),
  );
  await page.route('**/api/v1/recommendations/latest?*', (route) =>
    route.fulfill({
      status: 404,
      json: { error: { code: 'not_found', message: 'No on-demand batch' } },
    }),
  );
  await page.getByRole('link', { name: 'Data strategy', exact: true }).first().click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Discovery strategy' })).toContainText(
    'Data strategy',
  );
  await expect(
    page.getByRole('button', { name: 'Generate recommendations', exact: true }),
  ).toBeEnabled();
});
