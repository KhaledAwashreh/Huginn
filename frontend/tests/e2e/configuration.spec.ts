import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const PASSWORD = 'browser-only-correct-horse-battery';
async function login(page: Page, username: string): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
}
async function openSecurity(page: Page): Promise<void> {
  await page.locator('.user-menu-trigger').click();
  await page.getByRole('menuitem', { name: 'Security', exact: true }).click();
}

test('legacy configuration links lead to the single profile form', async ({ page }) => {
  await login(page, 'browser-config');
  for (const path of [
    '/account',
    '/professional-profile',
    '/offerings',
    '/offerings/new',
    '/strategies',
    '/strategies/new',
  ]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/profile$/);
    await expect(page.getByRole('heading', { name: 'Profile', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save profile', exact: true })).toBeVisible();
  }
  await expect(page.getByRole('combobox', { name: 'Discovery strategy', exact: true })).toHaveCount(
    0,
  );
});

test('password change in Security revokes all browser sessions', async ({
  page,
  browser,
  baseURL,
}) => {
  await login(page, 'browser-password');
  const other = await browser.newContext(baseURL ? { baseURL } : {});
  const otherPage = await other.newPage();
  await login(otherPage, 'browser-password');
  await openSecurity(page);
  await page.getByLabel('Current password', { exact: true }).fill(PASSWORD);
  await page
    .getByLabel('New password', { exact: true })
    .fill('changed-browser-password-with-no-creation-complexity');
  await page.getByRole('button', { name: 'Change password', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  expect((await otherPage.request.get('/api/v1/sessions/current')).status()).toBe(401);
  await other.close();
});

test('Security settings retain keyboard access and narrow layout', async ({ page }) => {
  await login(page, 'browser-visual');
  await openSecurity(page);
  await page.getByLabel('Current password', { exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('New password', { exact: true })).toBeFocused();
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== 'running'),
  );
  expect(
    (
      await new AxeBuilder({ page })
        .include('.settings-dialog')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 320, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await expect(page.getByRole('button', { name: 'Close settings' })).toBeVisible();
  await page.screenshot({ path: 'test-results/settings-security-narrow.png', fullPage: true });
});
