import { defineConfig, devices } from '@playwright/test';

const port = Number(process.env.PORT ?? 4301);
const liveMode = process.env.SOLMARA_HOME_E2E_MODE === 'live';
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './e2e',
  webServer: liveMode ? undefined : {
    command: 'pnpm build && node build',
    port,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      STATIC_METADATA_URL: 'http://127.0.0.1:9',
      SCENARIO_RUNNER_URL: 'http://127.0.0.1:9',
      PORT: String(port)
    }
  },
  use: {
    baseURL,
    trace: 'retain-on-failure'
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 5'] } }
  ]
});
