import { expect, test } from '@playwright/test';

const NAV_LINKS = ['Stories', 'Explorer', 'Purposes', 'Problem codes', 'Anatomy', 'Status'];

test('landing renders with header nav and every section in order', async ({ page }) => {
  const response = await page.goto('/');
  expect(response?.headers()['content-security-policy']).toContain("default-src 'self'");
  expect(response?.headers()['x-frame-options']).toBe('DENY');
  expect(response?.headers()['referrer-policy']).toBe('no-referrer');
  expect(response?.headers()['x-content-type-options']).toBe('nosniff');

  // Persistent synthetic-data banner and header nav on every page.
  await expect(page.getByText('Synthetic Solmara data')).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Visitor center pages' });
  for (const label of NAV_LINKS) {
    await expect(nav.getByRole('link', { name: label, exact: true })).toBeVisible();
  }

  await expect(page.getByRole('heading', { name: "Republic of Solmara Visitor's Center" })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Ask' })).toBeVisible();

  // Landing sections in document order: hero, doors, stories, nation, engineer, status.
  const sectionIds = await page.locator('main section[id]').evaluateAll((nodes) =>
    nodes.map((node) => node.id)
  );
  expect(sectionIds).toEqual(['purpose-lens', 'doors', 'stories', 'nation', 'engineer-door', 'status']);

  // Explorer, purposes, problem codes, anatomy are no longer landing sections.
  await expect(page.locator('main #explorer')).toHaveCount(0);
});

test('landing fits a mobile viewport without horizontal overflow', async ({ page }) => {
  await page.goto('/');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  await expect(page.getByRole('heading', { name: "Republic of Solmara Visitor's Center" })).toBeVisible();
});

test('reference routes render real content with a back link', async ({ page }) => {
  for (const path of ['/explorer', '/purposes', '/problem-codes', '/anatomy', '/changelog']) {
    const response = await page.goto(path);
    expect(response?.status(), path).toBe(200);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('link', { name: "Back to the Visitor's Center" })).toBeVisible();
  }
});

test('purposes page lists every purpose with plain language and working anchors', async ({ page }) => {
  await page.goto('/purposes');
  await expect(page.locator('.reference-card')).toHaveCount(6);
  // Each purpose is anchored by slug and carries its rule paragraph.
  await expect(page.locator('#child-benefit-review')).toBeVisible();
  await expect(page.locator('#child-benefit-review .plain')).not.toBeEmpty();
  // Denial codes link to the problem-code reference.
  await expect(
    page.locator('#child-benefit-review a[href="/problem-codes#pdp.purpose_not_permitted"]')
  ).toBeVisible();
});

test('problem-codes anchors resolve, including pdp.purpose_not_permitted', async ({ page }) => {
  await page.goto('/problem-codes#pdp.purpose_not_permitted');
  await expect(page.locator('[id="pdp.purpose_not_permitted"]')).toBeVisible();
  // The raw-row refusal a skeptic hits is documented too.
  await expect(page.locator('[id="request.invalid"]')).toBeVisible();
});

test('anatomy lists every relay and notary with repo config links', async ({ page }) => {
  await page.goto('/anatomy');
  await expect(page.locator('#relays .entity')).toHaveCount(6);
  await expect(page.locator('#notaries .entity')).toHaveCount(4);
  const configLink = page.locator('#cra-civil-relay a.config-link').first();
  await expect(configLink).toHaveAttribute('href', /github\.com.*relay\.yaml/);
  await expect(configLink.locator('code')).toContainText('ministries/interior-civil');
});

test('status grid shows the whole topology', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#status .status')).toHaveCount(14);
});

test('engineer door always shows the copy-as-curl examples', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#engineer-door .curl-example')).toHaveCount(4);
  // The skeptic wrong-purpose curl is one of them.
  await expect(page.locator('#engineer-door')).toContainText('pension-payment-review');
});

test('persona cards hand off to the portal with a persona query parameter', async ({ page }) => {
  await page.goto('/');
  const persona = page.locator('.persona-row a.persona-portal').first();
  await expect(persona).toHaveAttribute('href', /\?persona=[A-Za-z0-9-]+$/);
});

test('persona cards say what happens to each persona, linked to their story', async ({ page }) => {
  await page.goto('/');
  const outcomeLink = page.locator('.persona-row .persona-outcomes a').first();
  await expect(outcomeLink).toBeVisible();
  await expect(outcomeLink).toHaveAttribute('href', /^\/stories\/[a-z-]+(#[a-z-]+)?$/);
});

test('the nation map renders district labels on the committed district geometry', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.map .district').first()).toBeVisible();
  await expect(page.locator('.map .district-label').first()).toBeVisible();
  await expect(page.locator('.map .district-label', { hasText: 'Ketterin' })).toBeVisible();
});

test('explorer renders all five published artifact families from the live bundle', async ({ page }) => {
  test.skip(process.env.SOLMARA_HOME_E2E_MODE !== 'live', 'requires the live static-metadata bundle');
  await page.goto('/explorer');
  for (const id of ['api-catalog', 'datasets', 'services', 'offerings', 'policies']) {
    await expect(page.locator(`#${id}`)).toBeVisible();
  }
  await expect(page.locator('#offerings .entity').first()).toBeVisible();
  // Offerings cross-link to purposes.
  await expect(page.locator('#offerings a[href^="/purposes#"]').first()).toBeVisible();
});

test('engineer door publishes the synthetic demo tokens', async ({ page }) => {
  test.skip(process.env.SOLMARA_HOME_E2E_MODE !== 'live', 'demo tokens come from the container allowlist env');
  await page.goto('/');
  await expect(page.locator('#engineer-door .token').first()).toBeVisible();
  await expect(page.locator('#engineer-door .token-disclaimer')).toContainText('synthetic');
});

test('landing fails closed when the scenario runner is unavailable', async ({ page }) => {
  test.skip(process.env.SOLMARA_HOME_E2E_MODE === 'live', 'live compose mode has a healthy scenario runner');
  await page.goto('/');
  await expect(page.getByText('Scenario runner is unavailable', { exact: false }).first()).toBeVisible();
  // No stale story teasers rendered without live data.
  await expect(page.locator('.teaser')).toHaveCount(0);
});

test('purpose lens: first run reveals the naming moment and the flip produces a live denial code', async ({ page }) => {
  test.skip(process.env.SOLMARA_HOME_E2E_MODE !== 'live', 'requires a live scenario runner behind the stack');
  await page.goto('/');

  // Feel-before-name: no naming moment before the first run.
  await expect(page.locator('#purpose-limitation')).toHaveCount(0);

  await page.getByRole('button', { name: 'Ask' }).click();
  // Hydration must have run for the click to do anything; a missing naming
  // moment here means the page never hydrated, not just a slow backend.
  await expect(page.locator('#purpose-limitation')).toBeVisible({ timeout: 30_000 });

  // The flip: ask the same question under a purpose this notary does not permit.
  await page
    .locator('#purpose-limitation select')
    .selectOption('https://id.registrystack.org/solmara/purpose/pension-payment-review');
  await page.getByRole('button', { name: 'Ask under this purpose' }).click();
  const denialLink = page.locator('#purpose-limitation .problem a[href^="/problem-codes"]');
  await expect(denialLink).toBeVisible({ timeout: 30_000 });
});

test('story page: stepper runs an evaluate step and a purpose-denial step with a linked problem code', async ({ page }) => {
  test.skip(process.env.SOLMARA_HOME_E2E_MODE !== 'live', 'requires a live scenario runner behind the stack');
  await page.goto('/stories/birth-to-child-benefit');
  await expect(page.locator('.stepper .story-step').first()).toBeVisible();

  // A happy-path evaluate step returns a live result.
  await page.locator('#positive').getByRole('button', { name: 'Evaluate' }).click();
  await expect(page.locator('#positive .step-result')).toBeVisible({ timeout: 30_000 });

  // The former credential moment now shows ordinary application evidence. The
  // collector gathers source-owned predicates, but does not compose eligibility.
  await expect(page.locator('#credential .inspector')).toContainText('Evidence returned', { timeout: 30_000 });
  await expect(page.locator('#credential .inspector')).toContainText('child-benefit-federator');
  await expect(page.locator('#credential .inspector')).toContainText('Source authorities4');
  await expect(page.locator('#credential .inspector')).toContainText('not_composed');

  // The purpose-denial step is first-class and renders the stable problem code linked to /problem-codes.
  await page.locator('#purpose-denial').getByRole('button', { name: 'Try denial' }).click();
  const denialLink = page.locator('#purpose-denial .problem a[href^="/problem-codes"]');
  await expect(denialLink).toBeVisible({ timeout: 30_000 });
});

test('story page fits a mobile viewport without horizontal overflow', async ({ page }) => {
  test.skip(process.env.SOLMARA_HOME_E2E_MODE !== 'live', 'story pages require a live scenario runner to load');
  await page.goto('/stories/birth-to-child-benefit');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});
