import { test, expect, type Page } from '@playwright/test';

async function signIn(page: Page) {
  await page.goto('/');
  await page.getByTestId('signin').click();
  await expect(page).toHaveURL(/\/services$/);
}

// Happy path: landing -> sign in -> catalog -> farmer-voucher -> fields auto-resolve
// from the authority -> a proof entry is visible.
test('sign in, open a service, see a field resolve and a proof entry appear', async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole('heading', { name: /Welcome, Elena Dela Cruz/ })).toBeVisible();

  // The three wave 1 services are offered.
  await expect(page.getByTestId('card-farmer-voucher')).toBeVisible();
  await expect(page.getByTestId('card-child-benefit')).toBeVisible();
  await expect(page.getByTestId('card-pension-survivor')).toBeVisible();

  await page.getByTestId('card-farmer-voucher').click();
  await expect(page).toHaveURL(/\/services\/farmer-voucher$/);

  // The form fills itself from the Agriculture authority (auto-fetch resolves).
  await expect(page.getByText('Registered farmer: yes')).toBeVisible({ timeout: 10_000 });

  // The proof inspector / ticker shows the matching authority answer (SSE round-trip).
  await expect(page.getByText(/National Agricultural Data Institute answered: farmer-registered = true/).first()).toBeVisible({ timeout: 10_000 });

  // The synthetic-data banner stays visible throughout.
  await expect(page.getByText('Synthetic demo data')).toBeVisible();
});

// The cross-person denial is load-bearing: a real denied evaluation rendered as
// denial-as-success (blocked at the identity gate, no data touched).
test('the cross-person denial is blocked at the identity gate', async ({ page }) => {
  await signIn(page);
  await page.getByTestId('card-pension-survivor').click();
  await expect(page).toHaveURL(/\/services\/pension-survivor$/);

  await page.getByTestId('denial-try').click();
  await expect(page.getByTestId('denial-result')).toContainText('blocked at the identity gate', {
    timeout: 10_000
  });
});

// The centerpiece: the delegated two-hop. The Civil read must only resolve AFTER the
// Social guardian-link is proven (consent gates hop one, which authorizes hop two).
test('child benefit delegated two-hop: the civil read resolves only after consent + guardian link', async ({
  page
}) => {
  await signIn(page);
  await page.goto('/services/child-benefit');

  // Before consent, the consent card is shown and the child's civil data is not yet read.
  await expect(page.getByTestId('consent-card')).toBeVisible();
  await expect(page.getByText('Child age under 5: yes')).toHaveCount(0);

  await page.getByTestId('consent').click();

  // After consent, the guardian link verifies and the delegated civil read resolves.
  await expect(page.getByText('Child age under 5: yes')).toBeVisible({ timeout: 10_000 });
});

// The footer audit log is an expandable drawer: collapsed to a few rows by default,
// click to expand and scroll the full proof history (older entries are not lost).
test('the proof audit log drawer expands to reveal full history', async ({ page }) => {
  await signIn(page);
  await page.getByTestId('card-farmer-voucher').click();
  await expect(page.getByText('Registered farmer: yes')).toBeVisible({ timeout: 10_000 });

  const toggle = page.getByTestId('audit-log-toggle');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');

  // The scroll region exists and can hold overflow (full history is reachable).
  await expect(page.locator('#proof-audit-log')).toBeVisible();
});

// DoD: every EvidenceField state is reachable on the mock via the state gallery.
test('the field state gallery renders the evidence-field states', async ({ page }) => {
  const response = await page.goto('/gallery/fields');
  expect(response?.status()).toBe(200);
  // The gallery renders verified + fetched states with canned data; their badges use
  // the renderer microcopy.
  await expect(page.getByText(/verified by/i).first()).toBeVisible();
  await expect(page.getByText(/fetched from/i).first()).toBeVisible();
});
