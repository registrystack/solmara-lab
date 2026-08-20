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
const ESIGNET_LOGIN_PATH = '/login';

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

  await page.getByRole('button', { name: 'Verify with OTP' }).click();
  await page.getByRole('textbox', { name: 'UIN/VID' }).fill(DEMO_SUBJECT);
  const sendOtp = page.waitForResponse((response) => response.url().includes('/authorization/send-otp'));
  await page.getByRole('button', { name: 'Get OTP' }).click();
  await requireNoErrors(await sendOtp, 'send the demo OTP');

  await enterOtp(page);
  const authenticate = page.waitForResponse((response) => response.url().includes('/authenticate'));
  await page.getByRole('button', { name: /verify|continue/i }).click();
  await requireNoErrors(await authenticate, 'authenticate the demo identity');

  // Leaving the eSignet login means the OTP was accepted. What follows is either
  // the claim screen or the portal itself.
  await page.waitForURL((url) => url.pathname !== ESIGNET_LOGIN_PATH, { timeout: LOGIN_TIMEOUT_MS });
  await grantConsentIfAsked(page);
  await page.waitForURL((url) => url.pathname === CATALOG_PATH, { timeout: LOGIN_TIMEOUT_MS });
}

// eSignet reports a refused request as a 200 carrying an error list, so the
// response has to be read rather than trusted. An identity eSignet does not hold
// still passes send-otp and is only denied at authenticate, where the NIA Relay
// lookup answers, so both steps are checked. Naming the step is the whole
// message: the codes eSignet returns stay out of the smoke's output.
async function requireNoErrors(response: Response, step: string): Promise<void> {
  const body = (await response.json()) as { errors?: unknown[] };
  if (body.errors?.length) {
    throw new Error(`eSignet refused to ${step}`);
  }
}

// This eSignet build renders one input per OTP digit and advances the focus
// itself as each digit arrives, so the digits are typed into the field the
// component currently owns and paced to let that focus move. An older build
// renders a single input instead.
async function enterOtp(page: Page): Promise<void> {
  const digits = page.locator('input[type="tel"]');
  await digits.first().waitFor({ timeout: ATTEMPT_TIMEOUT_MS });
  if ((await digits.count()) === 1) {
    await digits.fill(DEMO_OTP);
    return;
  }
  for (const digit of DEMO_OTP) {
    await digits.first().press(digit);
    await page.waitForTimeout(100);
  }
}

// eSignet asks for claim consent the first time a subject signs in to this
// client and replays the stored consent on every later sign-in, so the flow
// either stops on the consent screen or carries on to the portal by itself.
async function grantConsentIfAsked(page: Page): Promise<void> {
  const consent = page.getByRole('button', { name: /allow|consent|continue|accept/i }).first();
  const catalog = page.getByRole('heading', { name: /^Welcome, / });
  await consent.or(catalog).first().waitFor({ timeout: LOGIN_TIMEOUT_MS });
  if (!(await consent.isVisible())) return;

  // Grant every claim the portal asked for. These are the synthetic profile
  // claims of the demo identity; the portal only keeps the subject and name.
  const allClaims = page.getByRole('checkbox', { name: 'voluntary_claims' });
  if (await allClaims.count()) {
    await allClaims.check({ force: true });
  } else {
    const claims = page.locator('input[type="checkbox"]');
    for (let index = 0; index < (await claims.count()); index += 1) {
      const claim = claims.nth(index);
      if (!(await claim.isChecked())) await claim.check({ force: true });
    }
  }
  await consent.click();
}
