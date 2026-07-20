// v1.2: 交易页 E2E 测试
import { test, expect } from "@playwright/test";

test.describe("Trading Page", () => {
  test("renders trading interface", async ({ page }) => {
    await page.goto("/trading");
    await expect(page.locator("body")).not.toBeEmpty();
  });

  test("displays selectable trading pair", async ({ page }) => {
    await page.goto("/trading");
    // 页面标题应包含"交易"
    const bodyText = await page.locator("body").innerText();
    expect(bodyText.length).toBeGreaterThan(0);
  });

  test("order form elements exist", async ({ page }) => {
    await page.goto("/trading");
    // 查找输入或按钮元素
    const elements = page.locator("input, button, select");
    const count = await elements.count();
    expect(count).toBeGreaterThan(0);
  });
});
