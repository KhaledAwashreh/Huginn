import { expect, test } from '@playwright/test';

test('legacy ICP overlaps are visible and removable and new overlaps are disabled', async ({
  page,
}) => {
  await page.goto('/login');
  await page.getByLabel('Username').fill('browser-icp-conflicts');
  await page.getByLabel('Password', { exact: true }).fill('browser-only-correct-horse-battery');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your workspace' })).toBeVisible();
  await page.goto('/icps/00000000-0000-0000-0000-000000000333');
  await expect(
    page.getByText('Analytics is both selected and excluded.', { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText('United States is both selected and excluded.', { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled();
  const industries = page.getByRole('combobox', {
    name: 'Collected industry options',
    exact: true,
  });
  await industries.focus();
  await industries.press('ArrowDown');
  const selectedIndustry = page.getByRole('option', { name: /^Analytics ·/ });
  await expect(selectedIndustry).toHaveAttribute('aria-selected', 'true');
  await industries.press('Space');
  await expect(selectedIndustry).toHaveAttribute('aria-selected', 'false');
  await industries.press('Escape');
  await expect(
    page.getByText('Analytics is both selected and excluded.', { exact: false }),
  ).toHaveCount(0);
  await industries.focus();
  await industries.press('ArrowDown');
  await expect(page.getByRole('option', { name: /^Analytics ·/ })).toHaveAttribute(
    'aria-disabled',
    'true',
  );
  await industries.press('Escape');
  const countries = page.getByRole('combobox', { name: 'Collected countries', exact: true });
  await countries.focus();
  await countries.press('ArrowDown');
  const selectedCountry = page.getByRole('option', { name: /^USA ·/ });
  await expect(selectedCountry).toHaveAttribute('aria-selected', 'true');
  await countries.press('Space');
  await expect(selectedCountry).toHaveAttribute('aria-selected', 'false');
  await countries.press('Escape');
  await expect(page.getByText('both selected and excluded', { exact: false })).toHaveCount(0);
  await countries.focus();
  await countries.press('ArrowDown');
  await expect(page.getByRole('option', { name: /^USA ·/ })).toHaveAttribute(
    'aria-disabled',
    'true',
  );
  await expect(page.getByRole('option', { name: /^United States ·/ })).toHaveAttribute(
    'aria-disabled',
    'true',
  );
  await countries.press('Escape');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled();
  const saved = await page.request.get(
    '/api/v1/ideal-client-profiles/00000000-0000-0000-0000-000000000333',
  );
  expect(saved.status()).toBe(200);
  const value = await saved.json();
  expect(value.industries).toEqual([]);
  expect(value.geographies).toEqual([]);
  expect(value.exclusions).toHaveLength(2);
});
