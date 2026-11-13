import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('profile edits real items in dialogs and disables what has no backend', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-bob');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Matches', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Profile', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Profile', exact: true })).toBeVisible();
  await expect(page.locator('main input, main textarea')).toHaveCount(0);

  const business = page.getByRole('region', { name: 'Your business', exact: true });
  await expect(business.getByRole('heading', { name: 'Your business', exact: true })).toBeVisible();
  await expect(business).toContainText('Business details are coming soon');
  await expect(page.getByRole('heading', { name: 'About your business' })).toBeVisible();
  const leadership = page.getByRole('region', { name: 'Leadership' });
  await expect(page.getByText('Client list is coming soon.')).toBeVisible();
  await expect(page.getByText('Links are coming soon.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Links', exact: true })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  for (const control of [
    page.getByRole('button', { name: 'Edit business details' }),
    page.getByRole('button', { name: 'Add a leader', exact: true }),
    leadership.getByRole('button', { name: /Bob Browser/ }),
    page.getByRole('button', { name: 'Add a client', exact: true }),
    page.getByRole('button', { name: 'Add a link', exact: true }),
  ]) {
    await expect(control).toBeDisabled();
    await expect(control).toHaveAttribute('title', 'Coming soon');
  }

  const dialog = page.getByRole('dialog');
  await page.getByRole('button', { name: 'Edit about your business' }).click();
  await dialog.getByLabel('Summary').fill('A small studio for early founders.');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('A small studio for early founders.')).toBeVisible();

  await page.getByRole('button', { name: 'Add a service', exact: true }).click();
  await dialog.getByLabel('Name').fill('Advising');
  await dialog.getByLabel('Description').fill('Monthly product advice.');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByRole('button', { name: /Advising/ })).toBeVisible();

  await page.getByRole('button', { name: /Advising/ }).click();
  await dialog.getByLabel('Name').fill('Advising plus');
  const renameRequest = page.waitForRequest(
    (request) => request.method() === 'PATCH' && request.url().includes('/offerings/'),
  );
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  expect((await renameRequest).postDataJSON()).toEqual({ name: 'Advising plus' });
  await expect(dialog).toHaveCount(0);
  await page.reload();
  await page.getByRole('button', { name: /Advising plus/ }).click();
  await expect(dialog.getByLabel('Name')).toHaveValue('Advising plus');
  await expect(dialog.getByLabel('Description')).toHaveValue('Monthly product advice.');
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();

  // The server commits, but the browser loses the create response.
  await page.getByRole('button', { name: 'Add a service', exact: true }).click();
  await dialog.getByLabel('Name').fill('Recovery planning');
  await dialog.getByLabel('Description').fill('A draft retained after a lost response.');
  await page.route(
    '**/api/v1/offerings',
    async (route) => {
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      await route.abort('failed');
    },
    { times: 1 },
  );
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('The outcome is uncertain.');
  await dialog.getByRole('button', { name: 'Refresh services', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('Your new service is still unconfirmed.');
  await expect(dialog.getByLabel('Name')).toHaveValue('Recovery planning');
  await expect(dialog.getByLabel('Description')).toHaveValue(
    'A draft retained after a lost response.',
  );
  await expect(dialog.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);
  page.once('dialog', (confirm) => confirm.accept());
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('button', { name: /Recovery planning/ })).toHaveCount(1);

  await page.getByRole('button', { name: 'Add your ICP', exact: true }).click();
  const icpDialog = page.getByRole('dialog', { name: 'ICP definition', exact: true });
  await icpDialog.getByLabel('Name').fill('Early founders');
  await icpDialog.getByRole('button', { name: '11-100', exact: true }).click();
  await icpDialog.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.locator('.icp-tile')).toContainText('Companies with 11-100 employees.');
  await expect(page.getByRole('button', { name: 'Add your ICP', exact: true })).toHaveCount(0);
  await icpDialog.getByRole('button', { name: 'Close settings' }).click();
  await expect(icpDialog).toHaveCount(0);
  await page.locator('.icp-tile').click();
  await expect(icpDialog.getByLabel('Name')).toHaveValue('Early founders');
  await expect(page).toHaveURL(/\/profile$/);
  await icpDialog.getByRole('button', { name: 'Close settings' }).click();

  // Tall settings content scrolls inside the modal rather than being clipped.
  await page.setViewportSize({ width: 1280, height: 500 });
  await page.getByRole('button', { name: 'Bob Browser' }).first().click();
  await page.getByRole('menuitem', { name: 'Account', exact: true }).click();
  const settingsBody = page.locator('.settings-body');
  await expect(page.getByLabel('Timezone (optional)')).toBeAttached();
  await settingsBody.evaluate((body) => body.scrollTo(0, body.scrollHeight));
  await expect.poll(() => settingsBody.evaluate((body) => body.scrollTop)).toBeGreaterThan(0);
  await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toBeInViewport();
  await page.getByRole('button', { name: 'Close settings' }).click();
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.reload();
  await expect(page.getByText('A small studio for early founders.')).toBeVisible();
  // Nothing about the features awaiting a backend persists in the browser.
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).filter((key) => key.startsWith('huginn.prototype')),
    ),
  ).toEqual([]);
  await page.getByRole('button', { name: /Advising/ }).click();
  page.once('dialog', (confirm) => confirm.accept());
  await dialog.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(page.getByRole('button', { name: /Advising/ })).toHaveCount(0);

  await page.getByRole('button', { name: 'Edit skills' }).click();
  await dialog.getByRole('button', { name: 'Add skill' }).click();
  await dialog.getByLabel('Skill 1').fill('Research');
  page.once('dialog', (confirm) => confirm.dismiss());
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).toBeVisible();
  page.once('dialog', (confirm) => confirm.accept());
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).toHaveCount(0);

  await page.getByRole('button', { name: 'Edit skills' }).click();
  await dialog.getByRole('button', { name: 'Add skill' }).click();
  await dialog.getByLabel('Skill 1').fill('Research, design');
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.reload();
  await page.getByRole('button', { name: 'Edit skills' }).click();
  await expect(dialog.getByLabel('Skill 1')).toHaveValue('Research, design');
  await expect(dialog.getByLabel('Skill 2')).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).toHaveCount(0);

  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== 'running'),
  );
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
});
