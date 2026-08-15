// v2.0: AI 实验室已合并到 /ai-factory（/ai-lab 是重定向桩），改为测试真实 AI 工厂页
import { test, expect } from "@playwright/test";

test.describe("AI Factory Page", () => {
  test("renders AI factory interface", async ({ page }) => {
    await page.goto("/ai-factory");
    await expect(page.locator("body")).not.toBeEmpty();
  });

  test("has goal/input fields", async ({ page }) => {
    await page.goto("/ai-factory");
    const inputs = page.locator("input, textarea");
    const count = await inputs.count();
    expect(count).toBeGreaterThan(0);
  });
});
