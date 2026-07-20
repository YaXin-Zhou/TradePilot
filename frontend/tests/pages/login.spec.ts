// v1.2: 登录页 E2E 测试
import { test, expect } from "@playwright/test";

test.describe("Login Page", () => {
  test("renders login form", async ({ page }) => {
    await page.goto("/login");
    // 检查登录页面基本结构
    const title = await page.title();
    expect(title).toBeTruthy();
  });

  test("has input fields", async ({ page }) => {
    await page.goto("/login");
    // 查找输入框（取决于实际 DOM 结构）
    const inputs = page.locator("input");
    const count = await inputs.count();
    expect(count).toBeGreaterThan(0);
  });

  test("has submit button", async ({ page }) => {
    await page.goto("/login");
    const buttons = page.locator("button");
    const count = await buttons.count();
    expect(count).toBeGreaterThan(0);
  });
});
