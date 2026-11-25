import { expect, test } from '@playwright/test';

test('the simplified profile completes a partial setup and activates discovery without a separate pairing step', async ({
  page,
}) => {
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-simple');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  const session = await (await page.request.get('/api/v1/sessions/current')).json();
  expect(session.simple_discovery_enabled).toBe(true);
  const icpResponse = await page.request.post('/api/v1/ideal-client-profiles', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: { name: 'Existing ICP', company_sizes: [{ band: '11-100' }] },
  });
  expect(icpResponse.status()).toBe(201);
  const existingIcp = await icpResponse.json();
  await page.getByRole('link', { name: 'Profile', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Existing ICP', exact: true })).toBeVisible();
  await page.getByLabel('Business name').fill('Product studio');
  await page
    .getByLabel('Tell us about your service')
    .fill('Research and design for product teams.');
  const save = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' && response.url().endsWith('/api/v1/me/business/setup'),
  );
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  expect((await save).status()).toBe(200);
  await expect(page.getByRole('status').filter({ hasText: 'Profile saved.' })).toBeVisible();
  const setup = await (await page.request.get('/api/v1/me/business/setup')).json();
  expect(setup.ideal_client_profile.id).toBe(existingIcp.id);
  const strategies = (
    await (await page.request.get('/api/v1/discovery-strategies?limit=100')).json()
  ).items;
  expect(strategies).toHaveLength(1);
  expect(strategies[0]).toMatchObject({
    is_active: true,
    service_offering_id: setup.service_offering.id,
    ideal_client_profile_id: existingIcp.id,
  });
  for (const path of ['/strategies', '/offerings/new', '/account', '/professional-profile']) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/profile$/);
  }
  await page.getByRole('link', { name: 'Recommendations', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Discovery strategy', exact: true })).toHaveCount(
    0,
  );
  const generate = page.getByRole('button', { name: 'Generate recommendations', exact: true });
  await expect(generate).toBeEnabled();
  const generated = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' && response.url().endsWith('/api/v1/recommendations'),
  );
  await generate.click();
  const response = await generated;
  expect(response.status()).toBe(201);
  expect(response.request().postDataJSON().strategy_id).toBe(strategies[0].id);
});
