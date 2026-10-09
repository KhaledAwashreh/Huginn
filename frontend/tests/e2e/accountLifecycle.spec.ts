import AxeBuilder from '@axe-core/playwright';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

type CapturedMail = { recipient: string; text: string };
const BROWSER_ORIGIN = `http://127.0.0.1:${process.env.HUGINN_BROWSER_PORT ?? '4173'}`;
const PASSWORD = 'SignUp!12345';
const NEW_PASSWORD = 'ResetNow1234567😀';

async function mailLink(request: APIRequestContext, recipient: string, path: string) {
  let link: string | undefined;
  await expect
    .poll(
      async () => {
        const response = await request.get(
          `http://127.0.0.1:${process.env.HUGINN_BROWSER_MAIL_PORT ?? '8025'}/messages`,
          {
            params: { recipient },
          },
        );
        expect(response.ok()).toBe(true);
        const messages = (await response.json()) as CapturedMail[];
        link = messages
          .flatMap((message) => message.text.split('\n'))
          .find((line) => line.startsWith(`${BROWSER_ORIGIN}${path}#token=`));
        return Boolean(link);
      },
      { timeout: 15_000 },
    )
    .toBe(true);
  if (!link) throw new Error('Expected mail link was not delivered');
  return link;
}

async function accessibleNarrowPage(page: Page, screenshot: string) {
  await page.setViewportSize({ width: 320, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({ path: `test-results/${screenshot}.png`, fullPage: true });
}

async function cleanProofHistory(page: Page, link: string) {
  const token = new URL(link).hash.slice('#token='.length);
  await expect(page).toHaveURL(new URL(link).pathname);
  expect(await page.evaluate(() => JSON.stringify(history.state))).not.toContain(token);
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual([]);
}

test('real signup mail, explicit verification and recovery keep the verified destination and revoke sessions', async ({
  page,
  browser,
}) => {
  test.setTimeout(90_000);
  const username = `lifecycle-${Date.now()}`;
  const email = `${username}@example.test`;
  const contactEmail = `${username}-contact@example.test`;
  const proofPosts: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/email-verifications'))
      proofPosts.push(request.url());
  });
  await page.goto('/create-account');
  for (const [label, value] of Object.entries({
    Username: username,
    Password: PASSWORD,
    'First name': 'Ada',
    'Last name': 'Lifecycle',
    Email: email,
  }))
    await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByLabel('Country of residence', { exact: true }).selectOption('US');
  await expect(page.getByLabel('Country calling code')).toHaveValue('+1');
  await expect(page.getByLabel('Country calling code')).toHaveAttribute('readonly');
  await page.getByLabel('Phone number', { exact: true }).fill('2025550123');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible();
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue(email);
  await accessibleNarrowPage(page, 'lifecycle-check-email');
  const verificationLink = await mailLink(page.request, email, '/verify-email');
  const preverification = await page.request.post('/api/v1/sessions', {
    data: { username, password: PASSWORD },
  });
  expect(preverification.status()).toBe(401);
  await page.goto(verificationLink);
  await expect(page.getByRole('button', { name: 'Verify email', exact: true })).toBeVisible();
  await cleanProofHistory(page, verificationLink);
  await accessibleNarrowPage(page, 'lifecycle-verify-ready');
  expect(proofPosts).toHaveLength(0);
  await page.reload();
  await expect(page.getByText('Open the link from your email', { exact: false })).toBeVisible();
  expect(proofPosts).toHaveLength(0);
  await page.goto(verificationLink);
  await page.getByRole('button', { name: 'Verify email', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Email verified' })).toBeVisible();
  expect(proofPosts).toHaveLength(1);
  await cleanProofHistory(page, verificationLink);
  await page.goto('/verify-email#token=second-verification-proof');
  await expect(page.getByRole('button', { name: 'Verify email', exact: true })).toBeVisible();
  expect(proofPosts).toHaveLength(1);
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('invalid or expired');
  expect(proofPosts).toHaveLength(2);
  await page.goto('/login');
  await page.goBack();
  await expect(page.getByText('Open the link from your email', { exact: false })).toBeVisible();
  await cleanProofHistory(page, verificationLink);
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
  const bootstrap = await page.request.get('/api/v1/sessions/current');
  expect(bootstrap.status()).toBe(200);
  const session = (await bootstrap.json()) as { csrf_token: string };
  const contactChange = await page.request.patch('/api/v1/me', {
    data: { email: contactEmail },
    headers: { 'X-CSRF-Token': session.csrf_token },
  });
  expect(contactChange.status()).toBe(200);
  const security = await page.request.get('/api/v1/me/account-security');
  expect(security.status()).toBe(200);
  expect((await security.json()).recovery_email).toBe(email);

  const recoveryContext = await browser.newContext({ baseURL: BROWSER_ORIGIN });
  try {
    const recovery = await recoveryContext.newPage();
    const resetPosts: string[] = [];
    recovery.on('request', (request) => {
      if (request.method() === 'POST' && request.url().endsWith('/password-resets/complete'))
        resetPosts.push(request.url());
    });
    await recovery.goto('/forgot-password');
    await recovery.getByLabel('Email').fill(email);
    await recovery.getByRole('button', { name: 'Request reset link', exact: true }).click();
    await expect(recovery.getByRole('heading', { name: 'Check your email' })).toBeVisible();
    const resetLink = await mailLink(recovery.request, email, '/reset-password');
    const contactMailbox = await recovery.request.get(
      `http://127.0.0.1:${process.env.HUGINN_BROWSER_MAIL_PORT ?? '8025'}/messages`,
      {
        params: { recipient: contactEmail },
      },
    );
    expect(await contactMailbox.json()).toEqual([]);
    await recovery.goto(resetLink);
    await expect(recovery.getByLabel('New password')).toBeVisible();
    await cleanProofHistory(recovery, resetLink);
    expect(resetPosts).toHaveLength(0);
    await accessibleNarrowPage(recovery, 'lifecycle-reset-ready');
    // Exercise form validation, allowing the submit handler past the native length guard.
    await recovery
      .getByLabel('New password')
      .evaluate((input) => input.removeAttribute('minlength'));
    await recovery.getByLabel('New password').fill('short');
    await recovery.getByRole('button', { name: 'Save password', exact: true }).click();
    await expect(recovery.getByRole('alert').first()).toBeVisible();
    await expect(recovery.getByLabel('New password')).toHaveValue('');
    expect(resetPosts).toHaveLength(0);
    await accessibleNarrowPage(recovery, 'lifecycle-reset-validation');
    await recovery.getByLabel('New password').fill(NEW_PASSWORD);
    await recovery.getByLabel('New password').focus();
    await recovery.keyboard.press('Tab');
    await expect(
      recovery.getByRole('button', { name: 'Save password', exact: true }),
    ).toBeFocused();
    await recovery.keyboard.press('Enter');
    await expect(recovery.getByRole('heading', { name: 'Password saved' })).toBeVisible();
    expect(resetPosts).toHaveLength(1);
    await accessibleNarrowPage(recovery, 'lifecycle-reset-saved');
    await recovery.goto('/reset-password#token=second-reset-proof');
    await expect(recovery.getByLabel('New password')).toBeVisible();
    expect(resetPosts).toHaveLength(1);
    await recovery.getByLabel('New password').fill(NEW_PASSWORD);
    await recovery.getByRole('button', { name: 'Save password', exact: true }).click();
    await expect(recovery.getByRole('alert')).toContainText('invalid or expired');
    expect(resetPosts).toHaveLength(2);
    expect((await page.request.get('/api/v1/sessions/current')).status()).toBe(401);
    await recovery.goto('/login');
    await recovery.getByLabel('Username').fill(username);
    await recovery.getByLabel('Password', { exact: true }).fill(PASSWORD);
    await recovery.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(recovery.getByRole('alert')).toBeVisible();
    await recovery.getByLabel('Password', { exact: true }).fill(NEW_PASSWORD);
    await recovery.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(recovery.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
  } finally {
    await recoveryContext.close();
  }
});

for (const route of ['/verify-email', '/reset-password']) {
  test(`reopening a ${route} mail link after reload restores its proof without submitting`, async ({
    page,
  }) => {
    const link = `${BROWSER_ORIGIN}${route}#token=browser-reopen-proof`;
    const proofControl =
      route === '/verify-email'
        ? page.getByRole('button', { name: 'Verify email', exact: true })
        : page.getByLabel('New password');
    let posts = 0;
    page.on('request', (request) => {
      if (request.method() === 'POST') posts += 1;
    });
    await page.goto(link);
    await expect(proofControl).toBeVisible();
    await cleanProofHistory(page, link);
    await page.reload();
    await expect(proofControl).toHaveCount(0);
    await page.goto(link);
    await expect(proofControl).toBeVisible();
    await cleanProofHistory(page, link);
    expect(posts).toBe(0);
  });
}

test('lifecycle forms support keyboard order and WCAG 2.2 AA checks at 320 CSS pixels', async ({
  page,
}) => {
  await page.goto('/create-account');
  await page.getByLabel('Username').focus();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Password', { exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('First name')).toBeFocused();
  await accessibleNarrowPage(page, 'lifecycle-create-account');
  for (const [route, screenshot] of [
    ['/forgot-password', 'lifecycle-forgot-password'],
    ['/verify-email', 'lifecycle-verify-missing'],
    ['/reset-password', 'lifecycle-reset-missing'],
  ]) {
    if (!route || !screenshot) throw new Error('Missing accessibility route');
    await page.goto(route);
    await accessibleNarrowPage(page, screenshot);
  }
  await page.goto('/forgot-password');
  await page.getByLabel('Email').focus();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Request reset link', exact: true })).toBeFocused();
});
