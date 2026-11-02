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
  await expect(page.getByText('9 of 9 stages finished', { exact: false })).toBeVisible();
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
  await expect(page.getByRole('heading', { name: 'Matches', exact: true })).toBeVisible();
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

test('matchmaking shows honest mixed outcomes and preserves a lost all-user receipt', async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(window.crypto, 'randomUUID', { configurable: true, value: undefined });
  });
  await page.goto('/admin/matchmaking');
  await page.getByLabel('Username').fill('browser-admin');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Matchmaking', exact: true })).toBeVisible();
  await page.getByLabel('Search active users').fill('target-');
  await expect(page.getByText('105 users are currently eligible.', { exact: false })).toBeVisible();
  for (let index = 0; index < 5; index++)
    await page.getByRole('button', { name: 'More users', exact: true }).click();
  await page.getByRole('button', { name: /target-104/ }).click();
  await page.getByLabel('Search active users').fill('target-000');
  await expect(page.locator('.selected-user')).toContainText('target-104');
  await expect(page.getByRole('combobox', { name: 'Window preset' })).toContainText('Last 30 days');
  await page.getByRole('combobox', { name: 'Window preset' }).click();
  await page.getByRole('option', { name: 'Last 7 days', exact: true }).click();
  await expect(page.getByRole('listbox')).toHaveCount(0);
  await expect(page.getByText('UTC preview:', { exact: false })).toContainText('Z');
  await page.screenshot({
    path: 'test-results/admin-matchmaking-trigger-wide.png',
    fullPage: false,
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.goto('/admin/matchmaking/runs/00000000-0000-0000-0000-00000000238d');
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
  await page.goto('/admin/matchmaking');
  await page.getByLabel('All currently eligible users').check();
  const submitted: string[] = [];
  let loseReceipt = true;
  await page.route('**/api/v1/admin/matchmaking/runs', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    submitted.push(route.request().postData() ?? '');
    if (loseReceipt) {
      loseReceipt = false;
      const response = await route.fetch();
      expect(response.status()).toBe(202);
      return route.abort('failed');
    }
    return route.continue();
  });
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry this exact request' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start run', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Retry this exact request' }).click();
  await expect(page).toHaveURL(/\/admin\/matchmaking\/runs\//);
  await expect(page.getByText('0 / 105 users processed', { exact: true })).toBeVisible();
  expect(submitted).toHaveLength(2);
  expect(submitted[1]).toBe(submitted[0]);
  await page.route('**/api/v1/admin/matchmaking/runs/*', (route) =>
    route.fulfill({
      status: 403,
      contentType: 'application/json',
      body: JSON.stringify({
        error: { code: 'forbidden', message: 'Administrator access required', details: [] },
      }),
    }),
  );
  await expect(page.getByRole('heading', { name: 'Administrator access required' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Matchmaking', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Data collection', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Bob Browser' }).click();
  await expect(page.getByRole('menuitem', { name: 'Sign out', exact: true })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: 'Admin', exact: true })).toHaveCount(0);
});

test('the user menu opens admin tools and the top nav keeps navigation and drafts', async ({
  page,
}) => {
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-admin');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Matches', exact: true })).toBeVisible();
  const workspace = page.getByRole('navigation', { name: 'Workspace navigation', exact: true });
  await expect(workspace.locator('.p-megamenu-root-list a')).toHaveText(['Matches', 'Profile']);
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
  await workspace.getByRole('link', { name: 'Matches', exact: true }).click();
  await expect(page).toHaveURL(/\/matches$/);
  await workspace.getByRole('link', { name: 'Profile', exact: true }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await page.goto('/professional-profile');
  await page.getByLabel('Headline', { exact: true }).fill('Unsaved mobile draft');
  page.once('dialog', (dialog) => dialog.dismiss());
  await workspace.getByRole('link', { name: 'Matches', exact: true }).click();
  await expect(page).toHaveURL(/\/professional-profile$/);
  await expect(page.getByLabel('Headline', { exact: true })).toHaveValue('Unsaved mobile draft');
});
