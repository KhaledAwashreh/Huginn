import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import type { components } from '../../src/api/generated/schema';

type Strategy = components['schemas']['DiscoveryStrategyResponse'];

const faults = new WeakMap<Page, string[]>();
test.beforeEach(({ page }) => {
  const errors: string[] = [];
  faults.set(page, errors);
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('response', (response) => {
    if (response.status() >= 500)
      errors.push(`HTTP ${response.status()} ${new URL(response.url()).pathname}`);
  });
});
test.afterEach(({ page }) => {
  expect(faults.get(page) ?? []).toEqual([]);
});

async function login(page: Page, username: string): Promise<Record<string, string>> {
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  const response = await page.request.get('/api/v1/sessions/current');
  expect(response.status()).toBe(200);
  const session = (await response.json()) as components['schemas']['CurrentSessionResponse'];
  expect(session.simple_discovery_enabled).toBe(true);
  return { 'X-CSRF-Token': session.csrf_token };
}

async function choose(page: Page, label: string, option: string): Promise<void> {
  await page.getByRole('combobox', { name: label, exact: true }).click();
  await page.getByRole('option', { name: option, exact: true }).click();
  await expect(page.locator('.p-select-overlay')).toHaveCount(0);
}

async function strategies(page: Page): Promise<Strategy[]> {
  const response = await page.request.get('/api/v1/discovery-strategies?offset=0&limit=100');
  expect(response.status()).toBe(200);
  return (
    (await response.json()) as components['schemas']['PageResponse_DiscoveryStrategyResponse_']
  ).items;
}

test('a new business sets up one offering and ICP and generates without a strategy selector', async ({
  page,
}, info) => {
  const headers = await login(page, info.retry ? 'browser-simple-retry' : 'browser-simple');
  await expect(page.getByRole('combobox', { name: 'Discovery strategy', exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole('button', { name: 'Generate recommendations', exact: true }),
  ).toBeDisabled();
  await page
    .getByRole('link', { name: 'Set up discovery in Profile', exact: true })
    .first()
    .click();
  const setup = page.getByRole('region', { name: 'Discovery setup', exact: true });
  await expect(setup).toBeVisible();
  expect(await strategies(page)).toHaveLength(0);

  await setup.getByRole('button', { name: 'Add a service', exact: true }).click();
  const serviceDialog = page.getByRole('dialog', { name: 'Add a service', exact: true });
  await serviceDialog.getByLabel('Name', { exact: true }).fill('Product research');
  await serviceDialog
    .getByLabel('Description', { exact: true })
    .fill('Research and design for product teams.');
  await serviceDialog.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(serviceDialog).toHaveCount(0);

  await setup.getByRole('button', { name: 'Add your ICP', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'ICP definition', exact: true });
  await settings.getByLabel('Name (required)', { exact: true }).fill('Growing product teams');
  await settings.getByRole('button', { name: '11-100', exact: true }).click();
  const icpCreated = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' && response.url().endsWith('/ideal-client-profiles'),
  );
  await settings.getByRole('button', { name: 'Save changes', exact: true }).click();
  expect((await icpCreated).status()).toBe(201);
  await expect(settings.getByLabel('Name (required)', { exact: true })).toHaveValue(
    'Growing product teams',
  );
  await expect(settings.getByLabel('Name (required)', { exact: true })).toBeEnabled();
  await settings.getByRole('button', { name: 'Close settings', exact: true }).click();
  await expect(settings).toHaveCount(0);
  expect(await strategies(page)).toHaveLength(0);
  await choose(page, 'Service offering', 'Product research');
  await choose(page, 'ICP', 'Growing product teams');
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      response.url().endsWith('/discovery-strategies/single-configuration'),
  );
  await setup.getByRole('button', { name: 'Save discovery setup', exact: true }).click();
  expect((await saved).status()).toBe(200);
  await expect(
    setup.getByRole('button', { name: 'Edit service offering', exact: true }),
  ).toContainText('Product research');
  await expect(
    setup.getByRole('button', { name: 'Edit ICP definition', exact: true }),
  ).toContainText('Growing product teams');
  await expect(setup.getByRole('button', { name: 'Add a service', exact: true })).toHaveCount(0);
  const configured = await strategies(page);
  expect(configured).toHaveLength(1);
  expect(configured[0]?.is_active).toBe(true);
  await page.reload();
  await expect(
    setup.getByRole('button', { name: 'Edit service offering', exact: true }),
  ).toBeVisible();

  for (const width of [1280, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
    await page.screenshot({ path: `test-results/simple-profile-${width}.png`, fullPage: true });
  }
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.goto('/strategies');
  await expect(page).toHaveURL(/\/profile$/);
  await page.goto('/offerings/new');
  await expect(page).toHaveURL(/\/profile$/);
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
  const generatedResponse = await generated;
  expect(generatedResponse.request().postDataJSON().strategy_id).toBe(configured[0]?.id);
  expect(generatedResponse.status()).toBe(201);
  expect((await strategies(page)).map((item) => item.id)).toEqual(
    configured.map((item) => item.id),
  );
  const rejected = await page.request.post('/api/v1/recommendations', {
    headers,
    data: { strategy_id: '00000000-0000-0000-0000-000000000000', limit: 10 },
  });
  expect([400, 404, 409, 422]).toContain(rejected.status());
});

test('existing multiple pairings require a choice and preserve unselected records', async ({
  page,
}, info) => {
  const headers = await login(
    page,
    info.retry ? 'browser-simple-legacy-retry' : 'browser-simple-legacy',
  );
  const created: Strategy[] = [];
  for (const suffix of ['A', 'B']) {
    const offeringResponse = await page.request.post('/api/v1/offerings', {
      headers,
      data: { name: `Legacy service ${suffix}`, description: `Retained offering ${suffix}` },
    });
    expect(offeringResponse.status()).toBe(201);
    const offering =
      (await offeringResponse.json()) as components['schemas']['ServiceOfferingResponse'];
    const icpResponse = await page.request.post('/api/v1/ideal-client-profiles', {
      headers,
      data: { name: `Legacy ICP ${suffix}`, company_sizes: [{ band: '11-100' }] },
    });
    expect(icpResponse.status()).toBe(201);
    const icp = (await icpResponse.json()) as components['schemas']['IdealClientProfileResponse'];
    const strategyResponse = await page.request.post('/api/v1/discovery-strategies', {
      headers,
      data: {
        name: `Internal legacy ${suffix}`,
        service_offering_id: offering.id,
        ideal_client_profile_id: icp.id,
        is_active: true,
      },
    });
    expect(strategyResponse.status()).toBe(201);
    created.push((await strategyResponse.json()) as Strategy);
  }
  await page.reload();
  await expect(page.getByRole('combobox', { name: 'Discovery strategy', exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole('button', { name: 'Generate recommendations', exact: true }),
  ).toBeDisabled();
  expect((await strategies(page)).filter((item) => item.is_active)).toHaveLength(2);
  await page.getByRole('link', { name: 'Profile', exact: true }).click();
  const setup = page.getByRole('region', { name: 'Discovery setup', exact: true });
  await expect(
    setup.getByRole('button', { name: 'Save discovery setup', exact: true }),
  ).toBeDisabled();
  await choose(page, 'Service offering', 'Legacy service B');
  await choose(page, 'ICP', 'Legacy ICP B');
  await setup.getByRole('button', { name: 'Save discovery setup', exact: true }).click();
  await expect(
    setup.getByRole('button', { name: 'Edit service offering', exact: true }),
  ).toContainText('Legacy service B');
  await expect(
    setup.getByRole('button', { name: 'Edit ICP definition', exact: true }),
  ).toContainText('Legacy ICP B');
  const after = await strategies(page);
  expect(after.map((item) => item.id).sort()).toEqual(created.map((item) => item.id).sort());
  expect(after.filter((item) => item.is_active).map((item) => item.id)).toEqual([created[1]?.id]);
  await setup.getByRole('button', { name: 'Edit ICP definition', exact: true }).click();
  const settings = page.getByRole('dialog', { name: 'ICP definition', exact: true });
  await expect(settings.getByLabel('Name (required)', { exact: true })).toHaveValue('Legacy ICP B');
  await settings.getByLabel('Name (required)', { exact: true }).fill('Selected legacy ICP B');
  const patch = page.waitForResponse(
    (response) =>
      response.request().method() === 'PATCH' &&
      response.url().endsWith(`/ideal-client-profiles/${created[1]?.ideal_client_profile_id}`),
  );
  await settings.getByRole('button', { name: 'Save changes', exact: true }).click();
  expect((await patch).status()).toBe(200);
  await expect(settings.getByLabel('Name (required)', { exact: true })).toBeEnabled();
  await settings.getByRole('button', { name: 'Close settings', exact: true }).click();
  const untouched = await page.request.get(
    `/api/v1/ideal-client-profiles/${created[0]?.ideal_client_profile_id}`,
  );
  expect((await untouched.json()).name).toBe('Legacy ICP A');
  await page.reload();
  await expect(
    setup.getByRole('button', { name: 'Edit ICP definition', exact: true }),
  ).toContainText('Selected legacy ICP B');
});
