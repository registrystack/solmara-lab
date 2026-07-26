import { expect, test } from '@playwright/test';

const NAV_LINKS = ['How it works', 'Stories', 'Citizen demo', 'Developers', 'Status'];

const evaluationUrl = (configuredUrl: string | undefined, fallbackUrl: string) =>
  `${(configuredUrl ?? fallbackUrl).replace('127.0.0.1', 'localhost').replace(/\/+$/, '')}/v1/evaluations`;

test('landing renders with header nav and every section in order', async ({ page }) => {
  const response = await page.goto('/');
  expect(response?.headers()['content-security-policy']).toContain("default-src 'self'");
  expect(response?.headers()['x-frame-options']).toBe('DENY');
  expect(response?.headers()['referrer-policy']).toBe('no-referrer');
  expect(response?.headers()['x-content-type-options']).toBe('nosniff');

  // Persistent synthetic-data banner and header nav on every page.
  await expect(page.getByText('Synthetic Solmara data')).toBeVisible();
  await expect(page.locator('.brand-mark')).toHaveText('SL');
  await expect(page.locator('.brand-copy')).toContainText('Registry Stack demo');
  const nav = page.getByRole('navigation', { name: 'Solmara Lab pages' });
  for (const label of NAV_LINKS) {
    await expect(nav.getByRole('link', { name: label, exact: true })).toBeVisible();
  }

  await expect(
    page.getByRole('heading', {
      name: "Get the answer a public service needs, without handing over the person's records."
    })
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Run the child-benefit example' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run the live review' })).toBeVisible();

  // Landing sections follow one story-first path. Full country, developer, and
  // status inventories own dedicated routes.
  const sectionIds = await page.locator('main section[id]').evaluateAll((nodes) =>
    nodes.map((node) => node.id)
  );
  expect(sectionIds).toEqual([
    'hero',
    'proof',
    'how-it-works',
    'purpose-lens',
    'stories',
    'citizen-demo',
    'developer-preview',
    'solmara-preview',
    'status-preview'
  ]);

  await expect(page.locator('main #engineer-door')).toHaveCount(0);
  await expect(page.locator('main #nation')).toHaveCount(0);
  await expect(page.locator('#stories .standards')).toHaveCount(0);
});

test('landing fits a mobile viewport without horizontal overflow', async ({ page }) => {
  await page.goto('/');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Get the answer');
});

test('reference routes render real content with a back link', async ({ page }) => {
  for (const path of ['/explorer', '/purposes', '/problem-codes', '/anatomy', '/changelog']) {
    const response = await page.goto(path);
    expect(response?.status(), path).toBe(200);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Developer reference pages' }).getByRole('link')).toHaveCount(5);
    await expect(page.getByRole('link', { name: 'Back to the developer workspace' })).toBeVisible();
  }
});

test('reference surfaces stay scannable and fit a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ['/explorer', '/purposes', '/problem-codes', '/anatomy', '/changelog']) {
    await page.goto(path);
    await expect(page.locator('.reference-directory')).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(overflow, path).toBe(false);
  }

  await page.goto('/anatomy');
  await expect(page.locator('.config-drawer').first()).not.toHaveAttribute('open', '');

  await page.goto('/changelog');
  await expect(page.locator('.change-detail').first()).not.toHaveAttribute('open', '');
});

test('country, developer, and status inventories have dedicated routes', async ({ page }) => {
  for (const path of ['/country', '/developers', '/status']) {
    const response = await page.goto(path);
    expect(response?.status(), path).toBe(200);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  }

  await page.goto('/country');
  await expect(page.locator('#nation .persona')).toHaveCount(12);

  await page.goto('/developers');
  await expect(page.locator('#engineer-door .curl-example')).toHaveCount(4);
  await expect(page.locator('#engineer-door')).toContainText('pension-payment-review');

  await page.goto('/status');
  await expect(page.locator('#status .status')).toHaveCount(17);
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
  await expect(page.locator('#notaries .entity')).toHaveCount(6);
  const craLinks = page.locator('#cra-civil-relay a.config-link');
  await expect(craLinks.filter({ hasText: 'projects/cra-civil/registry-stack.yaml' })).toHaveAttribute(
    'href',
    /github\.com.*projects\/cra-civil\/registry-stack\.yaml/
  );
  await expect(
    craLinks.filter({ hasText: 'runtime/registry-projects/local/cra-civil/relay/relay.yaml' })
  ).toHaveAttribute('href', /github\.com.*relay\/relay\.yaml/);
  await expect(craLinks.filter({ hasText: 'ministries/interior-civil' })).toHaveAttribute(
    'href',
    /github\.com.*ministries\/interior-civil/
  );
});

test('status grid shows the whole topology', async ({ page }) => {
  await page.goto('/status');
  await expect(page.locator('#status .status')).toHaveCount(17);
});

test('engineer door always shows the copy-as-curl examples', async ({ page }) => {
  await page.goto('/developers');
  await expect(page.locator('#engineer-door .curl-example')).toHaveCount(4);
  // The skeptic wrong-purpose curl is one of them.
  await expect(page.locator('#engineer-door')).toContainText('pension-payment-review');
});

test('persona cards hand off to the portal with a persona query parameter', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#citizen-demo .citizen-card')).toHaveCount(3);
  const persona = page.locator('#citizen-demo a[href*="?persona="]').first();
  await expect(persona).toHaveAttribute('href', /\?persona=[A-Za-z0-9-]+$/);
});

test('persona cards say what happens to each persona, linked to their story', async ({ page }) => {
  await page.goto('/');
  const outcomeLink = page.locator('#citizen-demo .story-outcome-link').first();
  await expect(outcomeLink).toBeVisible();
  await expect(outcomeLink).toHaveAttribute('href', /^\/stories\/[a-z-]+(#[a-z-]+)?$/);
});

test('the nation map renders district labels on the committed district geometry', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#solmara-preview .map .district').first()).toBeVisible();
  await expect(page.locator('#solmara-preview .map .district-label').first()).toBeVisible();
  await expect(page.locator('#solmara-preview .map .district-label', { hasText: 'Ketterin' })).toBeVisible();
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
  await page.goto('/developers');
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

test('purpose lens: the live review reveals evidence and the wrong-purpose challenge is refused', async ({ page }) => {
  test.skip(process.env.SOLMARA_HOME_E2E_MODE !== 'live', 'requires a live scenario runner behind the stack');
  await page.goto('/');

  // The boundary challenge appears only after a successful live evidence run.
  await expect(page.locator('#purpose-limitation')).toHaveCount(0);

  await page.getByRole('button', { name: 'Run the live review' }).click();
  await expect(page.locator('#purpose-limitation')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('#purpose-lens .result-lead')).toContainText('No source records were shared');

  // The request card sizes to its content instead of stretching to match the
  // denser result card and leaving a large dead area below the caption.
  const requestDeadSpace = await page.locator('#purpose-lens .lens-request').evaluate((card) => {
    const caption = card.querySelector('.quiet-caption');
    if (!caption) return Number.POSITIVE_INFINITY;
    return card.getBoundingClientRect().bottom - caption.getBoundingClientRect().bottom;
  });
  expect(requestDeadSpace).toBeLessThan(80);

  // Alternate purposes and raw requests stay out of the primary flow. When the
  // visitor opens them, the native select remains bounded by its card and uses
  // readable story labels instead of long identifier-heavy option labels.
  const advanced = page.locator('#purpose-limitation .advanced-request');
  await expect(advanced).not.toHaveAttribute('open', '');
  await advanced.locator(':scope > summary').click();
  const purposeSelect = advanced.getByLabel('Alternate purpose');
  await expect(purposeSelect).toBeVisible();
  const selectFits = await purposeSelect.evaluate((select) => {
    const selectRect = select.getBoundingClientRect();
    const cardRect = select.closest('.purpose-picker')?.getBoundingClientRect();
    return Boolean(cardRect && selectRect.width <= cardRect.width);
  });
  expect(selectFits).toBe(true);
  await expect(advanced.locator('.request-inspector')).not.toHaveAttribute('open', '');

  // The default challenge reuses the evidence request for pension review.
  await page.getByRole('button', { name: 'Try the wrong purpose' }).click();
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

test('citizen story renders runnable curls for each authority call', async ({ page }) => {
  test.skip(process.env.SOLMARA_HOME_E2E_MODE !== 'live', 'requires a live scenario runner behind the stack');
  await page.goto('/stories/citizen-self-service');

  await page.locator('#positive').getByRole('button', { name: 'Evaluate' }).click();
  const result = page.locator('#positive .step-result');
  await expect(result).toBeVisible({ timeout: 30_000 });
  await result.getByText('Technical detail').click();

  const authorityRequests = result.locator('.request-list .peer-call');
  await expect(authorityRequests).toHaveCount(2);
  await expect(authorityRequests.getByRole('button', { name: 'Copy as curl' })).toHaveCount(2);
  await expect(authorityRequests.nth(0)).toContainText(
    evaluationUrl(process.env.CRA_NOTARY_URL, 'http://localhost:4325')
  );
  await expect(authorityRequests.nth(1)).toContainText(
    evaluationUrl(process.env.NIA_NOTARY_URL, 'http://localhost:4326')
  );
  await expect(result).not.toContainText('solmara://authority-notaries');
});

test('story page fits a mobile viewport without horizontal overflow', async ({ page }) => {
  test.skip(process.env.SOLMARA_HOME_E2E_MODE !== 'live', 'story pages require a live scenario runner to load');
  await page.goto('/stories/birth-to-child-benefit');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});
