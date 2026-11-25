import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('the minimal profile saves business, service and ICP together and reuses the same setup on edits', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-bob');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Profile', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Profile', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Professional summary' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Add a service' })).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Discovery strategy', exact: true })).toHaveCount(
    0,
  );
  const personalBefore = await (await page.request.get('/api/v1/me/professional-profile')).json();
  await page.getByLabel('Business name').fill('Early-stage product studio');
  await page.getByLabel('Your name').fill('Bob Browser');
  await page
    .getByLabel('Tell us about your service')
    .fill('Research and product design for small teams.');
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByText('Define your ICP before saving your profile.')).toBeVisible();
  await page.getByRole('button', { name: 'Define your ICP', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Your ICP definition', exact: true });
  await dialog.getByLabel('Name (required)', { exact: true }).fill('Growing product teams');
  await dialog.getByRole('button', { name: '11-100', exact: true }).click();
  await dialog.getByRole('button', { name: 'Apply ICP', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(
    (await (await page.request.get('/api/v1/discovery-strategies?limit=100')).json()).items,
  ).toHaveLength(0);
  const saving = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' && response.url().endsWith('/api/v1/me/business/setup'),
  );
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  expect((await saving).status()).toBe(200);
  await expect(page.getByRole('status').filter({ hasText: 'Profile saved.' })).toBeVisible();
  const first = await (await page.request.get('/api/v1/me/business/setup')).json();
  expect(first.business.name).toBe('Early-stage product studio');
  expect(first.service_offering.description).toBe('Research and product design for small teams.');
  expect(first.ideal_client_profile.name).toBe('Growing product teams');
  expect(first.ideal_client_profile.company_sizes).toEqual([{ band: '11-100' }]);
  const beforeStrategies = (
    await (await page.request.get('/api/v1/discovery-strategies?limit=100')).json()
  ).items;
  expect(beforeStrategies).toHaveLength(1);
  expect(beforeStrategies[0]).toMatchObject({
    is_active: true,
    service_offering_id: first.service_offering.id,
    ideal_client_profile_id: first.ideal_client_profile.id,
  });
  expect(await (await page.request.get('/api/v1/me/professional-profile')).json()).toEqual(
    personalBefore,
  );

  await page.getByRole('button', { name: 'Edit ICP', exact: true }).click();
  await dialog.getByLabel('Name (required)', { exact: true }).fill('Discard these changes');
  await dialog.getByRole('button', { name: 'Cancel ICP changes', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Growing product teams', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Edit ICP', exact: true }).click();
  await expect(dialog.getByLabel('Name (required)', { exact: true })).toHaveValue(
    'Growing product teams',
  );
  await dialog.getByLabel('Name (required)', { exact: true }).fill('Focused product teams');
  await dialog.getByRole('button', { name: 'Apply ICP', exact: true }).click();
  await page
    .getByLabel('Tell us about your service')
    .fill('Product strategy and design for engineering teams.');
  const updating = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' && response.url().endsWith('/api/v1/me/business/setup'),
  );
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  expect((await updating).status()).toBe(200);
  await expect(page.getByRole('status').filter({ hasText: 'Profile saved.' })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Tell us about your service')).toHaveValue(
    'Product strategy and design for engineering teams.',
  );
  const after = await (await page.request.get('/api/v1/me/business/setup')).json();
  expect(after.service_offering.id).toBe(first.service_offering.id);
  expect(after.ideal_client_profile.id).toBe(first.ideal_client_profile.id);
  expect(after.ideal_client_profile.name).toBe('Focused product teams');
  const afterStrategies = (
    await (await page.request.get('/api/v1/discovery-strategies?limit=100')).json()
  ).items;
  expect(afterStrategies.map((item: { id: string }) => item.id)).toEqual(
    beforeStrategies.map((item: { id: string }) => item.id),
  );
  for (const width of [1280, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
    await page.screenshot({ path: `test-results/profile-${width}.png`, fullPage: true });
  }
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole('button', { name: 'Bob Browser', exact: true }).click();
  await expect(page.getByRole('menuitem', { name: 'ICP definition' })).toHaveCount(0);
  await expect(page.getByRole('menuitem', { name: 'Account', exact: true })).toHaveCount(0);
  await page.getByRole('menuitem', { name: 'Security', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Security', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
