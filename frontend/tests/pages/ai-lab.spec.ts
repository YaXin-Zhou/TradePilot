// v1.2: AI 实验室 E2E 测试
import { test, expect } from "@playwright/test";

test.describe("AI Lab Page", () => {
  test("renders AI lab interface", async ({ page }) => {
    await page.goto("/ai-lab");
    await expect(page.locator("body")).not.toBeEmpty();
  });

  test("has goal input field", async ({ page }) => {
    await page.goto("/ai-lab");
    const inputs = page.locator("input, textarea");
    const count = await inputs.count();
    expect(count).toBeGreaterThan(0);
  });
});
