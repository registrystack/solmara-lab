// The eSignet sign-in the portal e2e suite drives is the same one the hosted
// smoke checks, so both import this module. It stays free of runtime imports
// from @playwright/test: the smoke drives a browser it launched itself, outside
// the test runner. It also keeps every eSignet detail out of the errors it
// throws, because the smoke's output is a fixed line on a delivery record.
import type { Page, Response } from '@playwright/test';

// The portal's auth provider is server-side configuration the browser cannot
// read, so the suite discovers it from where the sign-in lands: the mock
// provider binds a persona session and continues straight to the catalog, while
// eSignet redirects to its own login and asks the citizen for an OTP. Driving
// whichever answers lets one suite run against a mock build and against a
// hosted deployment.
export type AuthMode = 'mock' | 'esignet';

// The synthetic demo identity eSignet is seeded with. 2300018263 is Elena Dela
// Cruz, the same persona the mock session binds, so every assertion that
// follows a sign-in reads the same in both modes.
const DEMO_SUBJECT = process.env.ESIGNET_DEMO_SUBJECT || '2300018263';
const DEMO_OTP = process.env.ESIGNET_DEMO_OTP || '111111';

const CATALOG_PATH = '/services';
const ESIGNET_LOGIN_PATH = '/signin';

// One attempt to reach a provider, a few attempts before giving up, and the
// budget for the redirects back from eSignet. The sum has to stay inside the
// per-test timeout the config gives a live run, or a reissued request is cut
// off before it can answer.
const ATTEMPT_TIMEOUT_MS = 15_000;
const PROVIDER_TIMEOUT_MS = 60_000;
const LOGIN_TIMEOUT_MS = 30_000;

/** Sign in from the landing page and report which provider answered. */
export async function signIn(page: Page): Promise<AuthMode> {
  await page.goto('/');
  const mode = await beginSignIn(page);
  await completeSignIn(page, mode);
  return mode;
}

/**
 * Click the sign-in on the page already loaded and report which provider
 * answered. Callers that only apply to one provider use this to decide before
 * paying for a full login.
 */
export async function beginSignIn(page: Page): Promise<AuthMode> {
  await page.getByTestId('signin').click();
  const deadline = Date.now() + PROVIDER_TIMEOUT_MS;
  for (;;) {
    try {
      await page.waitForURL(
        (url) => url.pathname === CATALOG_PATH || url.pathname === ESIGNET_LOGIN_PATH,
        { timeout: ATTEMPT_TIMEOUT_MS }
      );
      return new URL(page.url()).pathname === CATALOG_PATH ? 'mock' : 'esignet';
    } catch (err) {
      // eSignet refuses an authorization request while it is still starting and
      // the refusal is terminal for that request, so the whole request has to be
      // reissued rather than waited out. Past the deadline the timeout stands.
      if (Date.now() >= deadline) throw err;
      await page.goto('/auth/login');
    }
  }
}

/** Finish an eSignet sign-in. A mock sign-in is already complete. */
export async function completeSignIn(page: Page, mode: AuthMode): Promise<void> {
  if (mode === 'mock') return;

  await requestEsignetOtp(page);
  await requireNoErrors(await verifyEsignetOtp(page), 'authenticate the demo identity');

  // The engine renders consent on the same /signin route as the OTP form.
  await grantEsignetConsent(page);
  await page.waitForURL((url) => url.pathname === CATALOG_PATH, { timeout: LOGIN_TIMEOUT_MS });
}

/** Reach the OTP challenge through the real engine flow. */
export async function requestEsignetOtp(page: Page, subject = DEMO_SUBJECT): Promise<void> {
  await page.locator('input[name="username"]').fill(subject);
  const [sendOtp] = await Promise.all([
    page.waitForResponse(isFlowResponse),
    page.getByRole('button', { name: 'Send code', exact: true }).click()
  ]);
  await requireNoErrors(sendOtp, 'send the demo OTP');
}

/** Submit a challenge and return its response for positive and refusal proofs. */
export async function verifyEsignetOtp(page: Page, otp = DEMO_OTP): Promise<Response> {
  await enterOtp(page, otp);
  const [authenticate] = await Promise.all([
    page.waitForResponse(isFlowResponse),
    page.getByRole('button', { name: 'Verify', exact: true }).click()
  ]);
  return authenticate;
}

function isFlowResponse(response: Response): boolean {
  return new URL(response.url()).pathname.endsWith('/flow/execute') && response.request().method() === 'POST';
}

// The flow engine can return an application failure in a successful HTTP
// response. Keep identity data and provider error details out of smoke output.
async function requireNoErrors(response: Response, step: string): Promise<void> {
  const body: unknown = await response.json();
  if (!response.ok() || !body || typeof body !== 'object' ||
    ('flowStatus' in body && body.flowStatus === 'ERROR') ||
    ('error' in body && body.error) ||
    ('errors' in body && Array.isArray(body.errors) && body.errors.length > 0)) {
    throw new Error(`eSignet refused to ${step}`);
  }
}

// OTP_INPUT uses one input per digit. Fill each field directly when segmented.
async function enterOtp(page: Page, otp: string): Promise<void> {
  const digits = page.getByRole('textbox', { name: /^Verification code digit \d+$/ });
  await digits.first().waitFor({ timeout: ATTEMPT_TIMEOUT_MS });
  if ((await digits.count()) === 1) {
    await digits.fill(otp);
    return;
  }
  for (let index = 0; index < otp.length; index += 1) {
    await digits.nth(index).fill(otp[index]);
  }
}

// The native lab contract requires a fresh consent decision on every sign-in.
// Reaching the catalog without this prompt must fail the live browser proof.
async function grantEsignetConsent(page: Page): Promise<void> {
  const consent = page.getByRole('button', { name: 'Continue', exact: true }).first();
  await consent.waitFor({ timeout: LOGIN_TIMEOUT_MS });

  // Grant every claim the portal asked for. These are the synthetic profile
  // claims of the demo identity; the portal only keeps the subject and name.
  const allClaims = page.getByRole('checkbox', { name: 'voluntary_claims' });
  if (await allClaims.count()) {
    if (!(await allClaims.isChecked())) await allClaims.locator('xpath=..').click();
  } else {
    const claims = page.locator('input[type="checkbox"]');
    for (let index = 0; index < (await claims.count()); index += 1) {
      const claim = claims.nth(index);
      if (!(await claim.isChecked()) && !(await claim.isDisabled())) await claim.locator('xpath=..').click();
    }
  }
  await consent.click();
}
