import type { Page } from '@playwright/test';

const CATALOG_PATH = '/services';

// The portal signs in with its mock login: the sign-in button binds a persona
// session server-side and continues straight to the catalog.
const LOGIN_TIMEOUT_MS = 30_000;

/** Sign in from the landing page and wait for the catalog. */
export async function signIn(page: Page): Promise<void> {
  await page.goto('/');
  await beginSignIn(page);
}

/**
 * Click the sign-in on the page already loaded and wait for the catalog.
 * Callers that arrive with a persona hint load the landing page themselves.
 */
export async function beginSignIn(page: Page): Promise<void> {
  await page.getByTestId('signin').click();
  await page.waitForURL((url) => url.pathname === CATALOG_PATH, { timeout: LOGIN_TIMEOUT_MS });
}
