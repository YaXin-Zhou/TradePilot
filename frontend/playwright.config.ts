// v1.2: Playwright E2E 测试配置
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/pages",
  fullyParallel: true,
  retries: 1,
  workers: 1,
  reporter: "html",
  timeout: 30000,
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 30000,
  },
});
