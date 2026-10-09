import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
const PASSWORD = 'browser-only-correct-horse-battery';
async function login(page: Page, username: string): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
}
async function csrf(page: Page): Promise<string> {
  const response = await page.request.get('/api/v1/sessions/current');
  expect(response.status()).toBe(200);
  const session = (await response.json()) as { csrf_token: string };
  return session.csrf_token;
}
test('live owner CRUD, explicit clears, nested shape, bounded references, delete conflicts and dirty navigation', async ({
  page,
  browser,
  baseURL,
}) => {
  await login(page, 'browser-config');
  const proof = await csrf(page);
  const headers = { 'X-CSRF-Token': proof };
  await page.goto('/offerings/new');
  await page.getByLabel('Name (required)').fill('Strategy offering');
  await page
    .getByLabel('Description (required)')
    .fill('A realistic long description for an independent service provider. '.repeat(15));
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page).toHaveURL(/\/offerings\/[0-9a-f-]+$/);
  const offering = { id: new URL(page.url()).pathname.split('/').at(-1) ?? '' };
  await page.getByLabel('Name (required)').fill('Strategy offering updated');
  const offeringPatch = page.waitForRequest(
    (request) =>
      request.method() === 'PATCH' && request.url().endsWith(`/offerings/${offering.id}`),
  );
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  expect((await offeringPatch).postDataJSON()).toEqual({ name: 'Strategy offering updated' });
  await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled();
  const icpResponse = await page.request.post('/api/v1/ideal-client-profiles', {
    headers,
    data: {
      name: 'Structured ICP',
      industries: [{ name: 'Software' }, { name: 'Software' }],
      company_sizes: [{ band: '11-100' }],
      geographies: [
        { kind: 'country', value: 'US' },
        { kind: 'region', value: 'Europe' },
      ],
      exclusions: [
        { kind: 'industry', name: 'Consulting' },
        { kind: 'company', company_id: 'b30fb2f5-e3eb-4d28-b91b-619f2ac57d7f' },
        { kind: 'geography', geography: { kind: 'country', value: 'CA' } },
      ],
    },
  });
  expect(icpResponse.status()).toBe(201);
  const icp = (await icpResponse.json()) as { id: string };
  for (let index = 0; index < 101; index++) {
    expect(
      (
        await page.request.post('/api/v1/offerings', {
          headers,
          data: { name: `Paged offering ${index}`, description: 'Pagination fixture' },
        })
      ).status(),
    ).toBe(201);
  }
  await page.goto('/strategies/new');
  await page.getByLabel('Name', { exact: true }).fill('UI strategy');
  await expect(page.getByRole('button', { name: 'Load more service offerings' })).toBeVisible();
  await page.getByRole('button', { name: 'Load more service offerings' }).click();
  await expect(page.getByRole('button', { name: 'Load more service offerings' })).not.toBeVisible();
  await page.getByLabel('Service offering', { exact: true }).click();
  await page.getByRole('option', { name: 'Strategy offering updated', exact: true }).click();
  await page.getByLabel('ICP', { exact: true }).click();
  await page.getByRole('option', { name: 'Structured ICP', exact: true }).click();
  await page.getByRole('button', { name: 'Create strategy', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Discovery strategies', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Inactive', { exact: true })).toBeVisible();
  await page.goto('/offerings');
  const row = page.getByRole('row').filter({ hasText: 'Strategy offering updated' });
  await row.getByRole('button', { name: 'Delete', exact: true }).click();
  await page.getByRole('button', { name: 'Delete offering', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toBeVisible();
  expect((await page.request.get(`/api/v1/offerings/${offering.id}`)).status()).toBe(200);
  await page.getByRole('button', { name: 'Keep offering', exact: true }).click();
  await page.goto('/account');
  await page.getByLabel('Timezone (optional)').fill('');
  const patch = page.waitForRequest(
    (request) => request.method() === 'PATCH' && request.url().endsWith('/api/v1/me'),
  );
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  expect((await patch).postDataJSON()).toEqual({ timezone: null });
  await expect(page.getByLabel('First name', { exact: true })).toBeEnabled();
  await page.getByRole('link', { name: 'Professional profile', exact: true }).click();
  await page.getByLabel('Headline', { exact: true }).fill('Independent consultant');
  await page.getByRole('button', { name: 'Add skill', exact: true }).click();
  await page.getByLabel('Skill 1').fill('Research');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled();
  await page.getByLabel('Headline', { exact: true }).fill('');
  await page.getByRole('button', { name: 'Remove skill', exact: true }).click();
  const profilePatch = page.waitForRequest(
    (request) =>
      request.method() === 'PATCH' && request.url().endsWith('/api/v1/me/professional-profile'),
  );
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  expect((await profilePatch).postDataJSON()).toEqual({ headline: null, skills: [] });
  await page.getByLabel('Headline', { exact: true }).fill('Dirty local draft');
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('link', { name: 'Account & security', exact: true }).click();
  await expect(page.getByLabel('Headline', { exact: true })).toHaveValue('Dirty local draft');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  const other = await browser.newContext(baseURL ? { baseURL } : {});
  const otherPage = await other.newPage();
  await login(otherPage, 'browser-bob');
  const otherProof = await csrf(otherPage);
  expect((await otherPage.request.get(`/api/v1/offerings/${offering.id}`)).status()).toBe(404);
  expect(
    (
      await otherPage.request.patch(`/api/v1/ideal-client-profiles/${icp.id}`, {
        headers: { 'X-CSRF-Token': otherProof },
        data: { name: 'Other owner' },
      })
    ).status(),
  ).toBe(404);
  await otherPage.goto(`/offerings/${offering.id}`);
  await expect(otherPage.getByRole('alert')).toContainText(/not available|could not|no longer/i);
  await other.close();
});
test('password change revokes all browser sessions using current/new legacy contract', async ({
  page,
  browser,
  baseURL,
}) => {
  await login(page, 'browser-password');
  const other = await browser.newContext(baseURL ? { baseURL } : {});
  const otherPage = await other.newPage();
  await login(otherPage, 'browser-password');
  await page.goto('/account');
  await page.getByLabel('Current password', { exact: true }).fill(PASSWORD);
  await page
    .getByLabel('New password', { exact: true })
    .fill('changed-browser-password-with-no-creation-complexity');
  await page.getByRole('button', { name: 'Change password', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  expect((await otherPage.request.get('/api/v1/sessions/current')).status()).toBe(401);
  await other.close();
});
test('configuration wide/narrow layouts expose labels, keyboard focus and safe long content', async ({
  page,
}) => {
  await login(page, 'browser-visual');
  await page.goto('/account');
  await page.getByLabel('First name', { exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Last name', { exact: true })).toBeFocused();
  for (const route of [
    '/account',
    '/professional-profile',
    '/offerings/new',
    '/icps/new',
    '/strategies/new',
  ]) {
    await page.goto(route);
    if (route === '/icps/new') {
      await page.getByRole('combobox', { name: 'Collected industry options', exact: true }).focus();
      await page.keyboard.press('ArrowDown');
      await page
        .getByRole('searchbox', { name: 'Search collected industries', exact: true })
        .fill('Health');
      await page.getByRole('option', { name: /Healthcare/ }).click();
      await page.getByRole('combobox', { name: 'Collected industry options', exact: true }).focus();
      await page.keyboard.press('Escape');
      await expect(
        page.getByRole('combobox', { name: 'Collected industry options', exact: true }),
      ).toHaveAttribute('aria-expanded', 'false');
      await page.getByRole('combobox', { name: 'Collected countries', exact: true }).focus();
      await page.keyboard.press('ArrowDown');
      await page.getByRole('option', { name: /^USA ·/ }).click();
      await page.getByRole('combobox', { name: 'Collected countries', exact: true }).focus();
      await page.keyboard.press('Escape');
      await expect(
        page.getByRole('combobox', { name: 'Collected countries', exact: true }),
      ).toHaveAttribute('aria-expanded', 'false');
      await expect(page.getByRole('listbox')).toHaveCount(0);
      await page.getByRole('button', { name: '11-100', exact: true }).click();
      await expect(page.getByText('Healthcare', { exact: true })).toBeVisible();
      await expect(page.getByText('USA', { exact: true })).toBeVisible();
    }
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
          .analyze()
      ).violations,
    ).toEqual([]);
    if (route === '/icps/new') {
      await page.screenshot({
        path: 'test-results/configuration-icp-populated-wide.png',
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 320, height: 900 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/configuration-${route.replaceAll('/', '-')}-narrow.png`,
      fullPage: true,
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    if (route === '/icps/new') {
      await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    }
  }
  await page.goto('/professional-profile');
  await page.getByLabel('Summary', { exact: true }).fill('Long text and words '.repeat(100));
  await page.screenshot({ path: 'test-results/configuration-profile-wide.png', fullPage: true });
});
