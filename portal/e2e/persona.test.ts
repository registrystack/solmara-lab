import { test, expect } from '@playwright/test';

// The visitor center hands a persona into the portal as /?persona=<UIN>. The mock
// login must log in as that persona instead of always Elena Dela Cruz.
test('a persona handoff logs in as that persona', async ({ page }) => {
  await page.goto('/?persona=2300010248');

  // The landing acknowledges the handed-off persona before sign-in.
  await expect(page.getByTestId('persona-hint')).toContainText('Mateo Santos');

  await page.getByTestId('signin').click();
  await expect(page).toHaveURL(/\/services$/);

  // The authenticated catalog greets the handed-off persona, not the default.
  await expect(page.getByRole('heading', { name: /Welcome, Mateo Santos/ })).toBeVisible();
  await expect(page.getByText('Elena Dela Cruz')).toHaveCount(0);
});

// An unknown persona hint must fall back to the default session rather than forge
// a session for someone off the published roster.
test('an unknown persona hint falls back to the default session', async ({ page }) => {
  await page.goto('/?persona=9999999999');
  await expect(page.getByTestId('persona-hint')).toHaveCount(0);

  await page.getByTestId('signin').click();
  await expect(page).toHaveURL(/\/services$/);
  await expect(page.getByRole('heading', { name: /Welcome, Elena Dela Cruz/ })).toBeVisible();
});
