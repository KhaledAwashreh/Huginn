import { expect, test } from '@playwright/test';

const PASSWORD = 'browser-only-correct-horse-battery';

test('protected deep link, login, reload, mutation and logout use real cookie sessions', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.getByLabel('Username').fill('browser-ada');
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
  const bootstrap = await page.request.get('/api/v1/sessions/current');
  expect(bootstrap.status()).toBe(200);
  const session = (await bootstrap.json()) as { csrf_token: string };
  const mutation = await page.request.patch('/api/v1/me', {
    data: { first_name: 'Ada' },
    headers: { 'X-CSRF-Token': session.csrf_token },
  });
  expect(mutation.status()).toBe(200);
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual([]);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  expect((await page.request.get('/api/v1/sessions/current')).status()).toBe(401);
});

test('simultaneous tabs transition a legacy proof without invalidating each other', async ({
  context,
}) => {
  await context.addCookies([
    {
      name: 'huginn_management_session',
      value: 'legacy-browser-only-' + 'a'.repeat(64),
      url: `http://127.0.0.1:${process.env.HUGINN_BROWSER_PORT ?? '4173'}`,
      httpOnly: true,
      sameSite: 'Lax',
    },
  ]);
  const first = await context.newPage();
  const second = await context.newPage();
  await Promise.all([first.goto('/'), second.goto('/')]);
  await expect(first.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
  await expect(second.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
  const left = (await (await first.request.get('/api/v1/sessions/current')).json()) as {
    csrf_token: string;
  };
  const right = (await (await second.request.get('/api/v1/sessions/current')).json()) as {
    csrf_token: string;
  };
  expect(left.csrf_token).toBe(right.csrf_token);
  expect(left.csrf_token).not.toBe('legacy-browser-proof-' + 'b'.repeat(64));
  for (const page of [first, second]) {
    expect(
      (
        await page.request.patch('/api/v1/me', {
          data: { first_name: 'Legacy' },
          headers: { 'X-CSRF-Token': left.csrf_token },
        })
      ).status(),
    ).toBe(200);
  }
});

test('unsafe forbidden requests are not replayed or interpreted as logout', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-bob');
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
  const forbidden = await page.request.patch('/api/v1/me', { data: { first_name: 'No proof' } });
  expect(forbidden.status()).toBe(403);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
});
