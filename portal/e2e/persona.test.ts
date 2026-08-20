import { test, expect } from '@playwright/test';
import { beginSignIn, completeSignIn } from './support/auth';

const MOCK_ONLY = 'the persona handoff is mock-only: eSignet takes the subject from UserInfo';

// The visitor center hands a persona into the portal as /?persona=<UIN>. The mock
// login must log in as that persona instead of always Elena Dela Cruz.
test('a persona handoff logs in as that persona', async ({ page }) => {
  await page.goto('/?persona=2300010248');

  // The landing acknowledges the handed-off persona before sign-in.
  await expect(page.getByTestId('persona-hint')).toContainText('Mateo Santos');

  const mode = await beginSignIn(page);
  test.skip(mode === 'esignet', MOCK_ONLY);
  await completeSignIn(page, mode);
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

  const mode = await beginSignIn(page);
  test.skip(mode === 'esignet', MOCK_ONLY);
  await completeSignIn(page, mode);
  await expect(page).toHaveURL(/\/services$/);
  await expect(page.getByRole('heading', { name: /Welcome, Elena Dela Cruz/ })).toBeVisible();
});

// The same hint under eSignet must not reach the session: the subject comes from
// UserInfo, so a query parameter cannot sign anyone in as someone else.
test('eSignet ignores a persona handoff', async ({ page }) => {
  await page.goto('/?persona=2300010248');

  const mode = await beginSignIn(page);
  test.skip(mode === 'mock', 'the mock handoff is covered by the tests above');
  await completeSignIn(page, mode);
  await expect(page).toHaveURL(/\/services$/);

  await expect(page.getByRole('heading', { name: /Welcome, Mateo Santos/ })).toHaveCount(0);
});
