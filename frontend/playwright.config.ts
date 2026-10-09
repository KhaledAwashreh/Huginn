import { defineConfig, devices } from '@playwright/test';

const apiPort = Number(process.env.HUGINN_BROWSER_API_PORT ?? '8000');
const apiUrl = `http://127.0.0.1:${apiPort}`;
const browserPort = Number(process.env.HUGINN_BROWSER_PORT ?? '4173');
const browserUrl = `http://127.0.0.1:${browserPort}`;

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  outputDir: 'test-results',
  use: {
    baseURL: browserUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env.HUGINN_BROWSER_EXECUTABLE
      ? { executablePath: process.env.HUGINN_BROWSER_EXECUTABLE }
      : {},
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: '.venv/bin/python -m tests.browser_fixture',
      cwd: '..',
      url: `${apiUrl}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${browserPort} --strictPort`,
      url: browserUrl,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
