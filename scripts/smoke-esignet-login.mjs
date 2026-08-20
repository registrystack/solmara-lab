#!/usr/bin/env node

// The login itself lives in the portal e2e helper so the smoke and the suite
// drive one flow. Node strips the helper's types on import.
import { chromium } from '../portal/node_modules/@playwright/test/index.mjs';
import { signIn } from '../portal/e2e/support/auth.ts';

const portalUrl = (process.env.SOLMARA_PORTAL_PUBLIC_BASE_URL || 'http://127.0.0.1:4300').replace(/\/$/, '');

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ baseURL: portalUrl });
  const mode = await signIn(page);
  // A mock sign-in also reaches the catalog, so reaching it is not the check.
  // This smoke passes only when eSignet is the provider that answered.
  if (mode !== 'esignet') {
    throw new Error('the portal signed in without eSignet');
  }
  console.log('smoke-esignet-login: PASS');
} finally {
  await browser.close();
}
