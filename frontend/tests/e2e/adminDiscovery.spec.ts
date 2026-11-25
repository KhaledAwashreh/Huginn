import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const savedInvocation = '00000000-0000-0000-0000-000000002329';
const password = 'browser-only-correct-horse-battery';

// Axe reads colours mid-transition as low contrast, so scans wait for the page to settle.
async function waitForTransitions(page: Page): Promise<void> {
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== 'running'),
  );
}

test('collection console renders saved results, pages, keyboard tabs and private queue receipts', async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(window.crypto, 'randomUUID', { configurable: true, value: undefined });
  });
  await page.goto('/admin/pipeline');
  await page.getByLabel('Username').fill('browser-admin');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Data collection', exact: true })).toBeVisible();
  await page.goto(`/admin/pipeline/invocations/${savedInvocation}`);
  await expect(page.getByText('105 companies written by this run', { exact: true })).toBeVisible();
  await expect(page.getByText('12 of 12 stages finished', { exact: false })).toBeVisible();
  await page.getByRole('tab', { name: 'Source / Bronze' }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Silver', exact: true })).toBeFocused();
  await page.keyboard.press('End');
  await expect(page.getByRole('tab', { name: 'Gold', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await page.getByRole('button', { name: 'Next results' }).click();
  await expect(page.getByText('Results 51–100 of 105', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next results' }).click();
  await expect(page.getByText('Results 101–105 of 105', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Load next events' }).click();
  await expect(page.getByText('Saved harmless event 105:', { exact: false })).toBeVisible();
  await expect(page.locator('.event-log script')).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/admin-collection-wide.png', fullPage: false });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 320, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/admin-collection-narrow.png', fullPage: false });
  await page.goto('/admin/pipeline');
  await page.getByRole('button', { name: 'Pull data', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/pipeline\/invocations\//);
  await expect(page.getByText('queued', { exact: true }).first()).toBeVisible();
  const activeUrl = page.url();
  let activeReads = 0;
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/admin/pipeline/invocations/') && request.method() === 'GET')
      activeReads++;
  });
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const hiddenReads = activeReads;
  await page.waitForTimeout(3500);
  expect(activeReads).toBe(hiddenReads);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => activeReads).toBeGreaterThan(hiddenReads);
  await page.goto('/admin/pipeline');
  await page.getByRole('button', { name: 'Pull data', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Open active invocation' })).toBeVisible();
  expect(
    await page.getByRole('link', { name: 'Open active invocation' }).getAttribute('href'),
  ).toBe(new URL(activeUrl).pathname);
});

test('ordinary users cannot load admin projections or see admin navigation', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-bob');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Data collection', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Administration', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Bob Browser' }).click();
  await expect(page.getByRole('menuitem', { name: 'Security', exact: true })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: 'Admin', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.goto(`/admin/pipeline/invocations/${savedInvocation}`);
  await expect(page.getByRole('heading', { name: 'Administrator access required' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pull data', exact: true })).toHaveCount(0);
  const forbidden = await page.request.get('/api/v1/admin/pipeline/invocations');
  expect(forbidden.status()).toBe(403);
  expect(forbidden.headers()['cache-control']).toBe('no-store');
});

test('matchmaking history is read-only and keeps mixed saved outcomes', async ({ page }) => {
  const writerRequests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/admin/matchmaking/runs') && request.method() !== 'GET')
      writerRequests.push(`${request.method()} ${new URL(request.url()).pathname}`);
  });
  await page.goto('/admin/matchmaking');
  await page.getByLabel('Username').fill('browser-admin');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Matchmaking', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Run history', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start run', exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Search active users')).toHaveCount(0);
  const mixedRun = page.getByRole('row').filter({ hasText: 'completed_with_errors' });
  await expect(mixedRun).toContainText('105 / 105 processed');
  await expect(mixedRun.getByRole('link', { name: 'View run', exact: true })).toBeVisible();
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== 'running'),
  );
  await page.screenshot({
    path: 'test-results/admin-matchmaking-history-wide.png',
    fullPage: false,
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 320, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: 'test-results/admin-matchmaking-history-narrow.png',
    fullPage: false,
  });
  await mixedRun.getByRole('link', { name: 'View run', exact: true }).click();
  await expect(page.getByText('105 / 105 users processed', { exact: true })).toBeVisible();
  await expect(page.getByText('completed with errors', { exact: true })).toBeVisible();
  await expect(page.getByText('Some totals are unknown', { exact: false })).toBeVisible();
  await page
    .getByRole('button', { name: /^Show details for user / })
    .first()
    .click();
  await expect(page.locator('.skipped-list li')).toHaveCount(20);
  await page.locator('.skipped-list').getByRole('button', { name: 'More', exact: true }).click();
  await expect(page.locator('.skipped-list').getByText('Page 2', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== 'running'),
  );
  await page.screenshot({
    path: 'test-results/admin-matchmaking-results-wide.png',
    fullPage: false,
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 320, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: 'test-results/admin-matchmaking-results-narrow.png',
    fullPage: false,
  });
  expect(writerRequests).toEqual([]);

  const sessionResponse = await page.request.get('/api/v1/sessions/current');
  expect(sessionResponse.status()).toBe(200);
  const session = (await sessionResponse.json()) as { csrf_token: string };
  const retired = await page.request.post('/api/v1/admin/matchmaking/runs', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      request_id: '00000000-0000-0000-0000-000000000009',
      target: { kind: 'all_eligible' },
      cutoff: '2026-11-16T00:00:00Z',
      as_of: '2026-11-16T00:00:00Z',
    },
  });
  expect(retired.status()).toBe(410);
  expect(retired.headers()['cache-control']).toBe('no-store');
  expect(retired.headers()['vary']).toBe('Cookie');
  expect((await retired.json()).error.code).toBe('matchmaking_retired');
});

test('the user menu opens admin tools and the top nav keeps navigation and drafts', async ({
  page,
}) => {
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-admin');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  const workspace = page.getByRole('navigation', { name: 'Workspace navigation', exact: true });
  await expect(workspace.locator('.p-megamenu-root-list a')).toHaveText([
    'Recommendations',
    'Prospects',
    'Profile',
  ]);
  await expect(workspace.getByText('Data collection', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Bob Browser' }).click();
  await page.getByRole('menuitem', { name: 'Admin', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'Admin', exact: true });
  await expect(settings.getByRole('heading', { name: 'Matchmaking', exact: true })).toBeVisible();
  await settings.getByRole('button', { name: 'Open data collection', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/pipeline$/);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.goto('/admin');
  await expect(
    page.getByRole('heading', { name: 'Administration', exact: true, level: 1 }),
  ).toBeVisible();
  await page.getByRole('tab', { name: 'Overview', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Data collection', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/admin\/pipeline$/);
  await expect(page.getByRole('tab', { name: 'Data collection', exact: true })).toBeFocused();
  await page.keyboard.press('End');
  await expect(page.getByRole('tab', { name: 'Matchmaking', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/admin\/matchmaking$/);
  await expect(page.getByRole('tab', { name: 'Matchmaking', exact: true })).toBeFocused();
  await expect(page.getByRole('tab', { name: 'Matchmaking', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await page.getByRole('tab', { name: 'Data collection', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Data collection', exact: true })).toBeVisible();
  await page.goto(`/admin/pipeline/invocations/${savedInvocation}`);
  await expect(page.getByRole('tab', { name: 'Data collection', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await page.reload();
  await expect(page.getByRole('tab', { name: 'Data collection', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await page.goto('/admin');
  await expect(page.getByRole('link', { name: 'Open data collection', exact: true })).toBeVisible();
  await waitForTransitions(page);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({ path: 'test-results/administration-page-wide.png', fullPage: false });
  await page.setViewportSize({ width: 320, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: 'test-results/administration-nav-narrow.png', fullPage: false });
  await workspace.getByRole('link', { name: 'Recommendations', exact: true }).click();
  await expect(page).toHaveURL(/\/recommendations$/);
  await workspace.getByRole('link', { name: 'Prospects', exact: true }).click();
  await expect(page).toHaveURL(/\/prospects$/);
  await workspace.getByRole('link', { name: 'Profile', exact: true }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await page.getByLabel('Tell us about your service').fill('Unsaved business service draft.');
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.goBack();
  await expect(page).toHaveURL(/\/profile$/);
  await expect(page.getByLabel('Tell us about your service')).toHaveValue(
    'Unsaved business service draft.',
  );
});
