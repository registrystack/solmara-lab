#!/usr/bin/env node

import { chromium } from '../portal/node_modules/@playwright/test/index.mjs';

const portalUrl = (process.env.SOLMARA_PORTAL_PUBLIC_BASE_URL || 'http://127.0.0.1:4300').replace(/\/$/, '');
const subject = process.env.ESIGNET_DEMO_SUBJECT || '2300018263';
const otp = process.env.ESIGNET_DEMO_OTP || '111111';

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const deadline = Date.now() + 60_000;
  while (true) {
    await page.goto(`${portalUrl}/auth/login`);
    try {
      await page.getByRole('button', { name: 'Verify with OTP' }).waitFor({ timeout: 5_000 });
      break;
    } catch {
      // eSignet may still be starting. Retry the whole authorization request.
    }
    if (Date.now() >= deadline) {
      throw new Error('eSignet login did not become ready');
    }
    await page.waitForTimeout(1_000);
  }
  await page.getByRole('button', { name: 'Verify with OTP' }).click();
  await page.getByRole('textbox', { name: 'UIN/VID' }).fill(subject);
  const sendOtpResponse = page.waitForResponse((response) => response.url().includes('/authorization/send-otp'));
  await page.getByRole('button', { name: 'Get OTP' }).click();
  const sendOtp = await (await sendOtpResponse).json();
  if (Array.isArray(sendOtp.errors) && sendOtp.errors.length) {
    throw new Error('eSignet send-otp failed');
  }
  const otpInputs = page.locator('input[type="tel"]');
  if (await otpInputs.count() === 1) {
    await otpInputs.fill(otp);
  } else {
    for (const digit of otp) {
      await otpInputs.first().press(digit);
      await page.waitForTimeout(100);
    }
  }
  await page.getByRole('button', { name: /verify|continue/i }).click();
  const servicesUrl = `${portalUrl}/services`;
  await page.waitForURL((url) => url.href === servicesUrl || url.pathname.endsWith('/consent'), {
    timeout: 60_000,
  });
  if (page.url() !== servicesUrl) {
    const consent = page.getByRole('button', { name: /allow|consent|continue|accept/i });
    await consent.first().waitFor({ timeout: 10_000 });
    const claimCheckboxes = page.locator('input[type="checkbox"]');
    const allClaims = page.getByRole('checkbox', { name: 'voluntary_claims' });
    if (await allClaims.count()) {
      await allClaims.check({ force: true });
    } else {
      for (let index = 0; index < await claimCheckboxes.count(); index += 1) {
        const checkbox = claimCheckboxes.nth(index);
        if (!(await checkbox.isChecked())) await checkbox.check({ force: true });
      }
    }
    await consent.first().click();
  }
  await page.waitForURL(servicesUrl, { timeout: 60_000 });
  console.log('smoke-esignet-login: PASS');
} finally {
  await browser.close();
}
