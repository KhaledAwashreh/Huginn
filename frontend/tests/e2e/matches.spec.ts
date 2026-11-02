import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

async function login(page: Page, username: string): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Matches', exact: true })).toBeVisible();
}

test('owned matches, search and >100 pagination, current signals, safe links and isolation', async ({
  page,
  browser,
  baseURL,
}) => {
  await login(page, 'browser-matches');
  await page.getByRole('link', { name: 'Matches', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Matches', exact: true })).toBeVisible();
  await expect(page.getByTestId('match-row')).toHaveCount(50);
  await expect(page.getByTestId('match-row').first()).toContainText('Current match company 000');
  await page.getByRole('searchbox', { name: 'Search matches' }).fill('company 007');
  await expect(page.getByTestId('match-row')).toHaveCount(1);
  await page.getByRole('searchbox', { name: 'Search matches' }).fill('nothing like this');
  await expect(page.getByText('No matches on this page fit your search.')).toBeVisible();
  await expect(page.getByText('Search covers only the current page.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Next page', exact: true })).toBeEnabled();
  await page.getByRole('searchbox', { name: 'Search matches' }).fill('');
  await page.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page.getByTestId('match-row').first()).toContainText('Current match company 050');
  await page.getByRole('button', { name: 'First page', exact: true }).click();
  await expect(page.getByTestId('match-row').first()).toContainText('Current match company 000');
  const firstTile = page.getByTestId('match-row').first();
  for (const name of [/^Good match/, /^Not a fit/]) {
    const reaction = firstTile.getByRole('button', { name });
    await expect(reaction).toBeDisabled();
    await expect(reaction).toHaveAttribute('title', 'Coming soon');
  }
  await page.getByRole('link', { name: 'Profile', exact: true }).click();
  await page.getByRole('button', { name: 'Add your ICP', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'ICP definition', exact: true });
  await expect(settings.getByRole('heading', { name: 'From your feedback' })).toHaveCount(0);
  await expect(settings.getByRole('heading', { name: 'From your client list' })).toHaveCount(0);
  await settings.getByRole('button', { name: 'Close settings' }).click();
  await expect(settings).toHaveCount(0);
  await page.getByRole('link', { name: 'Matches', exact: true }).click();
  await expect(page.getByTestId('match-row').first()).toBeVisible();
  await page.mouse.move(0, 0);
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== 'running'),
  );
  await page.screenshot({ path: 'test-results/matches-list-wide.png', fullPage: true });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 320, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: 'test-results/matches-list-narrow.png', fullPage: true });
  await page.getByTestId('match-row').first().getByRole('link').click();
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Matches');
  await expect(
    page.getByRole('heading', { name: 'Current match company 000', exact: true }),
  ).toBeVisible();
  const matchId = new URL(page.url()).pathname.split('/').at(-1) ?? '';
  for (const name of [/^Good match/, /^Not a fit/]) {
    await expect(page.getByRole('button', { name })).toBeDisabled();
  }
  await expect(
    page.getByRole('heading', { name: 'Current company context', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Current company signals', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Stored notes <script>plain text</script>', { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId('signal-row')).toHaveCount(50);
  await expect(page.getByTestId('signal-row').first()).toContainText('Hiring context');
  await expect(page.locator('a[href^="javascript:"]')).toHaveCount(0);
  await expect(page.getByText('javascript:alert(1)', { exact: true })).toHaveCount(0);
  await expect(
    page.locator(
      'a[href="https://owner-match-0.example.test/"], a[href="https://owner-match-0.example.test"]',
    ),
  ).toHaveAttribute('rel', 'noopener noreferrer');
  const signals = page.getByTestId('match-signals');
  await signals.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page.getByTestId('signal-row').first()).toContainText('Current signal 050');
  await signals.getByRole('button', { name: 'Next page', exact: true }).click();
  await expect(page.getByTestId('signal-row')).toHaveCount(5);
  await page.screenshot({ path: 'test-results/matches-detail-narrow.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: 'test-results/matches-detail-wide.png', fullPage: true });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  const other = await browser.newContext(baseURL ? { baseURL } : {});
  const otherPage = await other.newPage();
  await login(otherPage, 'browser-bob');
  const denied = await otherPage.request.get('/api/v1/matches/' + matchId);
  const missing = await otherPage.request.get(
    '/api/v1/matches/00000000-0000-0000-0000-000000000001',
  );
  expect(denied.status()).toBe(404);
  expect(await denied.json()).toEqual(await missing.json());
  expect((await otherPage.request.get('/api/v1/matches/' + matchId + '/signals')).status()).toBe(
    404,
  );
  await otherPage.goto('/matches/' + matchId);
  await expect(otherPage.getByRole('alert')).toBeVisible();
  await expect(otherPage.getByText('Current match company 000', { exact: true })).toHaveCount(0);
  await other.close();
});
