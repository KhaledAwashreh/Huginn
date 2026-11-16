import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import type { components } from '../../src/api/generated/schema';

function watchBrowserBootstrap(page: Page): { errors: string[]; stop: () => void } {
  const errors: string[] = [];
  const onPageError = (error: Error) => errors.push(`pageerror:${error.name}`);
  const onConsole = (message: {
    type: () => string;
    location: () => { url: string };
    text: () => string;
  }) => {
    if (message.type() === 'error') {
      // Chromium reports ordinary HTTP error responses as a generic resource
      // message. Transport failures and server errors are captured separately.
      if (message.text().startsWith('Failed to load resource:')) return;
      const path = message.location().url ? new URL(message.location().url).pathname : 'unknown';
      errors.push(`console-error:${path}`);
    }
  };
  const onRequestFailed = (request: { method: () => string; url: () => string }) => {
    const path = new URL(request.url()).pathname;
    errors.push(`request-failed:${request.method()}:${path}`);
  };
  const onResponse = (response: { status: () => number; url: () => string }) => {
    if (response.status() >= 500)
      errors.push(`http-${response.status()}:${new URL(response.url()).pathname}`);
  };
  page.on('pageerror', onPageError);
  page.on('console', onConsole);
  page.on('requestfailed', onRequestFailed);
  page.on('response', onResponse);
  return {
    errors,
    stop: () => {
      page.off('pageerror', onPageError);
      page.off('console', onConsole);
      page.off('requestfailed', onRequestFailed);
      page.off('response', onResponse);
    },
  };
}

test('profile edits real items in dialogs and disables what has no backend', async ({ page }) => {
  const ownerBootstrap = watchBrowserBootstrap(page);
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-bob');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  ownerBootstrap.stop();
  expect(ownerBootstrap.errors).toEqual([]);
  const ownerSessionResponse = await page.request.get('/api/v1/sessions/current');
  expect(ownerSessionResponse.status()).toBe(200);
  const ownerSession =
    (await ownerSessionResponse.json()) as components['schemas']['CurrentSessionResponse'];
  const csrfHeaders = { 'X-CSRF-Token': ownerSession.csrf_token };
  const initialStrategiesResponse = await page.request.get(
    '/api/v1/discovery-strategies?offset=0&limit=100',
  );
  expect(initialStrategiesResponse.status()).toBe(200);
  const initialStrategies =
    (await initialStrategiesResponse.json()) as components['schemas']['PageResponse_DiscoveryStrategyResponse_'];
  expect(initialStrategies.items).toHaveLength(0);
  await page.getByRole('link', { name: 'Profile', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Profile', exact: true })).toBeVisible();
  await expect(page.locator('main input, main textarea')).toHaveCount(0);

  const business = page.getByRole('region', { name: 'Your business', exact: true });
  await expect(business.getByRole('heading', { name: 'Your business', exact: true })).toBeVisible();
  await expect(business).toContainText('Add a short description of your business.');
  const businessEditButton = page.getByRole('button', { name: 'Edit business details' });
  await expect(businessEditButton).toBeEnabled();
  const businessEditBounds = await businessEditButton.boundingBox();
  expect(businessEditBounds?.width).toBeGreaterThanOrEqual(24);
  expect(businessEditBounds?.height).toBeGreaterThanOrEqual(24);
  await expect(page.getByRole('heading', { name: 'About your business' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Professional summary' })).toBeVisible();
  const leadership = page.getByRole('region', { name: 'Leadership' });
  await expect(page.getByText('Client list is coming soon.')).toBeVisible();
  await expect(page.getByText('Links are coming soon.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Links', exact: true })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  for (const control of [
    page.getByRole('button', { name: 'Add a leader', exact: true }),
    leadership.getByRole('button', { name: /Bob Browser/ }),
    page.getByRole('button', { name: 'Add a client', exact: true }),
    page.getByRole('button', { name: 'Add a link', exact: true }),
  ]) {
    await expect(control).toBeDisabled();
    const descriptionId = await control.getAttribute('aria-describedby');
    expect(descriptionId).toBeTruthy();
    const reason = page.locator(`#${descriptionId}`);
    await expect(reason).toBeVisible();
    await expect(reason).not.toHaveText('');
    const bounds = await control.boundingBox();
    expect(bounds?.width).toBeGreaterThanOrEqual(24);
    expect(bounds?.height).toBeGreaterThanOrEqual(24);
  }
  await expect(page.locator('a[href="/icps"], a[href="/strategies"]')).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/profile-wide.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/profile-narrow.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 720 });

  const dialog = page.getByRole('dialog');
  const businessBeforeResponse = await page.request.get('/api/v1/me/business');
  expect(businessBeforeResponse.status()).toBe(200);
  const businessBefore =
    (await businessBeforeResponse.json()) as components['schemas']['BusinessProfileResponse'];
  expect(businessBefore).toMatchObject({
    owner_user_id: ownerSession.user_id,
    name: null,
    tagline: null,
    website: null,
    location: null,
    description: null,
    capabilities: null,
  });
  const userBeforeResponse = await page.request.get('/api/v1/me');
  expect(userBeforeResponse.status()).toBe(200);
  const userBefore = await userBeforeResponse.json();
  const personalBeforeResponse = await page.request.get('/api/v1/me/professional-profile');
  expect(personalBeforeResponse.status()).toBe(200);
  const personalBefore = await personalBeforeResponse.json();
  const configurationBefore = await Promise.all([
    page.request.get('/api/v1/offerings?offset=0&limit=100'),
    page.request.get('/api/v1/ideal-client-profiles?offset=0&limit=100'),
    page.request.get('/api/v1/discovery-strategies?offset=0&limit=100'),
  ]);
  for (const response of configurationBefore) expect(response.status()).toBe(200);

  await businessEditButton.focus();
  await page.keyboard.press('Enter');
  const businessDialog = page.getByRole('dialog', { name: 'Business details', exact: true });
  await businessDialog.getByLabel('Business name').fill('Early-stage product studio');
  await businessDialog.getByLabel('Tagline').fill('Research-led product decisions.');
  await businessDialog.getByLabel('Website').fill('https://studio.example.test');
  await businessDialog.getByLabel('Location').fill('Amman');
  await businessDialog
    .getByLabel('About your business')
    .fill('We help small teams find product direction.');
  await businessDialog.getByLabel('Capabilities').fill('Product strategy\nCustomer research');
  const businessPatchResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'PATCH' && response.url().endsWith('/api/v1/me/business'),
  );
  await businessDialog.getByRole('button', { name: 'Save changes', exact: true }).click();
  expect((await businessPatchResponse).status()).toBe(200);
  await expect(businessDialog).toHaveCount(0);
  const businessAfterResponse = await page.request.get('/api/v1/me/business');
  expect(businessAfterResponse.status()).toBe(200);
  const businessAfter =
    (await businessAfterResponse.json()) as components['schemas']['BusinessProfileResponse'];
  expect(businessAfter).toMatchObject({
    id: businessBefore.id,
    owner_user_id: ownerSession.user_id,
    name: 'Early-stage product studio',
    tagline: 'Research-led product decisions.',
    website: 'https://studio.example.test',
    location: 'Amman',
    description: 'We help small teams find product direction.',
    capabilities: [{ name: 'Product strategy' }, { name: 'Customer research' }],
  });
  await expect(business).toContainText('Early-stage product studio');
  await expect(business.getByRole('link', { name: 'studio.example.test' })).toHaveAttribute(
    'href',
    'https://studio.example.test/',
  );
  await expect(page.getByText('We help small teams find product direction.')).toBeVisible();
  const userAfterBusinessResponse = await page.request.get('/api/v1/me');
  const personalAfterBusinessResponse = await page.request.get('/api/v1/me/professional-profile');
  expect(await userAfterBusinessResponse.json()).toEqual(userBefore);
  expect(await personalAfterBusinessResponse.json()).toEqual(personalBefore);
  const configurationAfterBusiness = await Promise.all([
    page.request.get('/api/v1/offerings?offset=0&limit=100'),
    page.request.get('/api/v1/ideal-client-profiles?offset=0&limit=100'),
    page.request.get('/api/v1/discovery-strategies?offset=0&limit=100'),
  ]);
  expect(await Promise.all(configurationAfterBusiness.map((response) => response.json()))).toEqual(
    await Promise.all(configurationBefore.map((response) => response.json())),
  );

  await page.getByRole('button', { name: 'Edit professional summary' }).click();
  await dialog.getByLabel('Professional summary').fill('A personal summary for early founders.');
  const personalProfilePatch = page.waitForResponse(
    (response) =>
      response.request().method() === 'PATCH' &&
      response.url().endsWith('/api/v1/me/professional-profile'),
  );
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  expect((await personalProfilePatch).status()).toBe(200);
  await expect(page.getByText('A personal summary for early founders.')).toBeVisible();
  await expect(dialog).toHaveCount(0);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.screenshot({ path: 'test-results/profile-business-wide.png', fullPage: true });
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
      .toBe(true);
    await page.screenshot({ path: `test-results/profile-business-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.getByRole('button', { name: 'Add a service', exact: true }).click();
  await dialog.getByLabel('Name').fill('Advising');
  await dialog.getByLabel('Description').fill('Monthly product advice.');
  const advisingCreate = page.waitForResponse(
    (response) => response.request().method() === 'POST' && response.url().endsWith('/offerings'),
  );
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  expect((await advisingCreate).status()).toBe(201);
  const advising = (await (
    await advisingCreate
  ).json()) as components['schemas']['ServiceOfferingResponse'];
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
  await page.route('**/api/v1/ideal-client-profiles', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    await route.abort('failed');
  });
  await icpDialog.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(icpDialog.getByRole('alert')).toContainText('The save outcome is uncertain.');
  await page.unroute('**/api/v1/ideal-client-profiles');
  await icpDialog.getByRole('button', { name: 'Refresh saved data', exact: true }).click();
  await expect(icpDialog.getByRole('alert')).toContainText('create result is still uncertain');
  await expect(icpDialog.getByLabel('Name')).toHaveValue('Early founders');
  await expect(icpDialog.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled();
  await expect(page.locator('.icp-tile')).toContainText('Companies with 11-100 employees.');
  await expect(page.getByRole('button', { name: 'Add your ICP', exact: true })).toHaveCount(0);
  page.once('dialog', (confirm) => confirm.accept());
  await icpDialog.getByRole('button', { name: 'Close settings' }).click();
  await expect(icpDialog).toHaveCount(0);
  await page.locator('.icp-tile').click();
  await expect(icpDialog.getByLabel('Name')).toHaveValue('Early founders');
  await expect(page).toHaveURL(/\/profile$/);
  await icpDialog.getByRole('button', { name: 'Close settings' }).click();

  const firstIcpListResponse = await page.request.get(
    '/api/v1/ideal-client-profiles?offset=0&limit=100',
  );
  expect(firstIcpListResponse.status()).toBe(200);
  const firstIcpList =
    (await firstIcpListResponse.json()) as components['schemas']['PageResponse_IdealClientProfileResponse_'];
  const firstIcp = firstIcpList.items.find(({ name }) => name === 'Early founders');
  expect(firstIcp).toBeDefined();
  const secondIcpResponse = await page.request.post('/api/v1/ideal-client-profiles', {
    headers: csrfHeaders,
    data: { name: 'Second existing ICP' },
  });
  expect(secondIcpResponse.status()).toBe(201);
  const secondIcp =
    (await secondIcpResponse.json()) as components['schemas']['IdealClientProfileResponse'];
  const strategiesBeforeManualPairingResponse = await page.request.get(
    '/api/v1/discovery-strategies?offset=0&limit=100',
  );
  expect(strategiesBeforeManualPairingResponse.status()).toBe(200);
  const strategiesBeforeManualPairing =
    (await strategiesBeforeManualPairingResponse.json()) as components['schemas']['PageResponse_DiscoveryStrategyResponse_'];
  expect(strategiesBeforeManualPairing.items).toEqual(initialStrategies.items);
  const strategyResponse = await page.request.post('/api/v1/discovery-strategies', {
    headers: csrfHeaders,
    data: {
      name: 'Manual profile regression strategy',
      service_offering_id: advising.id,
      ideal_client_profile_id: secondIcp.id,
      is_active: false,
    },
  });
  expect(strategyResponse.status()).toBe(201);
  const manualStrategy =
    (await strategyResponse.json()) as components['schemas']['DiscoveryStrategyResponse'];
  const strategyStateBeforeProfileEdit = [
    {
      id: manualStrategy.id,
      service_offering_id: manualStrategy.service_offering_id,
      ideal_client_profile_id: manualStrategy.ideal_client_profile_id,
      is_active: manualStrategy.is_active,
    },
  ];

  const userBeforeBusinessClear = await (await page.request.get('/api/v1/me')).json();
  const personalBeforeBusinessClear = await (
    await page.request.get('/api/v1/me/professional-profile')
  ).json();
  const configurationBeforeBusinessClear = await Promise.all([
    page.request.get('/api/v1/offerings?offset=0&limit=100'),
    page.request.get('/api/v1/ideal-client-profiles?offset=0&limit=100'),
    page.request.get('/api/v1/discovery-strategies?offset=0&limit=100'),
  ]);
  for (const response of configurationBeforeBusinessClear) expect(response.status()).toBe(200);
  const businessClearDialog = page.getByRole('dialog', { name: 'Business details', exact: true });
  await page.getByRole('button', { name: 'Edit business details' }).click();
  await businessClearDialog.getByLabel('Tagline').fill('');
  await businessClearDialog.getByLabel('Website').fill('');
  await businessClearDialog.getByLabel('Location').fill('');
  await businessClearDialog.getByLabel('Capabilities').fill('');
  const businessClearRequest = page.waitForRequest(
    (request) => request.method() === 'PATCH' && request.url().endsWith('/api/v1/me/business'),
  );
  await businessClearDialog.getByRole('button', { name: 'Save changes', exact: true }).click();
  expect((await businessClearRequest).postDataJSON()).toEqual({
    tagline: null,
    website: null,
    location: null,
    capabilities: [],
  });
  await expect(businessClearDialog).toHaveCount(0);
  const clearedBusinessResponse = await page.request.get('/api/v1/me/business');
  expect(clearedBusinessResponse.status()).toBe(200);
  const clearedBusiness =
    (await clearedBusinessResponse.json()) as components['schemas']['BusinessProfileResponse'];
  expect(clearedBusiness).toMatchObject({
    id: businessBefore.id,
    owner_user_id: ownerSession.user_id,
    name: 'Early-stage product studio',
    tagline: null,
    website: null,
    location: null,
    description: 'We help small teams find product direction.',
    capabilities: [],
  });
  expect(await (await page.request.get('/api/v1/me')).json()).toEqual(userBeforeBusinessClear);
  expect(await (await page.request.get('/api/v1/me/professional-profile')).json()).toEqual(
    personalBeforeBusinessClear,
  );
  const configurationAfterBusinessClear = await Promise.all([
    page.request.get('/api/v1/offerings?offset=0&limit=100'),
    page.request.get('/api/v1/ideal-client-profiles?offset=0&limit=100'),
    page.request.get('/api/v1/discovery-strategies?offset=0&limit=100'),
  ]);
  expect(
    await Promise.all(configurationAfterBusinessClear.map((response) => response.json())),
  ).toEqual(await Promise.all(configurationBeforeBusinessClear.map((response) => response.json())));

  await page.getByRole('button', { name: /Advising plus/ }).click();
  await dialog.getByLabel('Description').fill('Monthly advice for a manually paired service.');
  const pairedServicePatch = page.waitForResponse(
    (response) =>
      response.request().method() === 'PATCH' &&
      response.url().endsWith(`/offerings/${advising.id}`),
  );
  await dialog.getByRole('button', { name: 'Save', exact: true }).click();
  expect((await pairedServicePatch).status()).toBe(200);

  await page.reload();
  const selectedIcpTile = page.getByRole('button').filter({ hasText: 'Second existing ICP' });
  await expect(selectedIcpTile).toBeVisible();
  await selectedIcpTile.focus();
  await page.keyboard.press('Enter');
  await expect(icpDialog.getByLabel('Name')).toHaveValue('Second existing ICP');
  await icpDialog.getByLabel('Name').fill('Selected second ICP');
  const selectedIcpPatch = page.waitForResponse(
    (response) =>
      response.request().method() === 'PATCH' &&
      response.url().endsWith(`/ideal-client-profiles/${secondIcp.id}`),
  );
  await icpDialog.getByRole('button', { name: 'Save changes', exact: true }).click();
  expect((await selectedIcpPatch).status()).toBe(200);
  await expect(icpDialog.getByLabel('Name')).toHaveValue('Selected second ICP');
  await expect(page.locator('.icp-tile').filter({ hasText: 'Early founders' })).toBeVisible();
  await expect(page.locator('.icp-tile').filter({ hasText: 'Selected second ICP' })).toBeVisible();
  await icpDialog.getByRole('button', { name: 'Close settings' }).click();

  const strategyListResponse = await page.request.get(
    '/api/v1/discovery-strategies?offset=0&limit=100',
  );
  expect(strategyListResponse.status()).toBe(200);
  const strategies =
    (await strategyListResponse.json()) as components['schemas']['PageResponse_DiscoveryStrategyResponse_'];
  expect(
    strategies.items.map(({ id, service_offering_id, ideal_client_profile_id, is_active }) => ({
      id,
      service_offering_id,
      ideal_client_profile_id,
      is_active,
    })),
  ).toEqual(strategyStateBeforeProfileEdit);

  const browser = page.context().browser();
  if (browser === null) throw new Error('The browser is unavailable for owner-isolation checks.');
  const otherContext = await browser.newContext({ baseURL: new URL(page.url()).origin });
  const otherPage = await otherContext.newPage();
  const otherBootstrap = watchBrowserBootstrap(otherPage);
  await otherPage.goto('/login');
  await otherPage.getByLabel('Username').fill('browser-config');
  await otherPage
    .getByLabel('Password', { exact: true })
    .fill('browser-only-correct-horse-battery');
  await otherPage.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(
    otherPage.getByRole('heading', { name: 'Recommendations', exact: true }),
  ).toBeVisible();
  otherBootstrap.stop();
  expect(otherBootstrap.errors).toEqual([]);
  const otherSessionResponse = await otherPage.request.get('/api/v1/sessions/current');
  expect(otherSessionResponse.status()).toBe(200);
  const otherSession =
    (await otherSessionResponse.json()) as components['schemas']['CurrentSessionResponse'];
  expect(otherSession.account_id).not.toBe(ownerSession.account_id);
  expect(otherSession.user_id).not.toBe(ownerSession.user_id);
  const otherBusinessResponse = await otherPage.request.get('/api/v1/me/business');
  expect(otherBusinessResponse.status()).toBe(200);
  const otherBusiness =
    (await otherBusinessResponse.json()) as components['schemas']['BusinessProfileResponse'];
  expect(otherBusiness.owner_user_id).toBe(otherSession.user_id);
  expect(otherBusiness.id).not.toBe(businessBefore.id);
  expect(otherBusiness).toMatchObject({
    name: null,
    tagline: null,
    website: null,
    location: null,
    description: null,
    capabilities: null,
  });
  const foreignIcpResponse = await otherPage.request.get(
    `/api/v1/ideal-client-profiles/${secondIcp.id}`,
  );
  expect(foreignIcpResponse.status()).toBe(404);
  await otherContext.close();

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
  await expect(page.getByText('A personal summary for early founders.')).toBeVisible();
  // Nothing about the features awaiting a backend persists in the browser.
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).filter((key) => key.startsWith('huginn.prototype')),
    ),
  ).toEqual([]);
  await page.getByRole('button', { name: /Recovery planning/ }).click();
  page.once('dialog', (confirm) => confirm.accept());
  await dialog.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(page.getByRole('button', { name: /Recovery planning/ })).toHaveCount(0);

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
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/profile-narrow-320.png', fullPage: true });
});
