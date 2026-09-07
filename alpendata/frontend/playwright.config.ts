import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  use: { baseURL: 'http://127.0.0.1:5195', launchOptions: { executablePath: process.env.ALPENDATA_TEST_BROWSER } },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: { command: `"${process.execPath}" node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5195 --strictPort`, port: 5195, reuseExistingServer: false },
});
