import { defineConfig } from '@playwright/test';

const port = Number(process.env.PORT ?? '4000');
const hostedMode = process.env.SOLMARA_PORTAL_E2E_MODE === 'hosted';
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://localhost:${port}`;

export default defineConfig({
  // The portal BFF is a single-process server whose proof feed is an in-process
  // store with a long-lived SSE feed on /proof/stream. Hosted sessions are scoped
  // per opaque cookie, but the e2e suite still runs serially so trace timing stays
  // deterministic across tests.
  workers: 1,
  fullyParallel: false,
  webServer: hostedMode ? undefined : {
    command: `pnpm build && PORT=${port} node build`,
    port,
    timeout: 120_000,
    reuseExistingServer: false
  },
  testDir: 'e2e',
  use: {
    baseURL
  }
});
