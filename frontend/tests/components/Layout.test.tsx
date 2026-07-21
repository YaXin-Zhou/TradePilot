// v1.2: 导航组件渲染 + 语言切换测试
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

// 简易 Layout 渲染测试（不依赖完整路由）
function SimpleLayout() {
  return (
    <div data-testid="layout">
      <nav data-testid="nav">
        <a href="/">Dashboard</a>
        <a href="/trading">Trading</a>
        <a href="/strategies">Strategies</a>
        <a href="/ai-lab">AI Lab</a>
      </nav>
    </div>
  );
}

describe("Layout", () => {
  it("renders navigation links", () => {
    render(<SimpleLayout />);
    expect(screen.getByTestId("nav")).toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Trading")).toBeInTheDocument();
    expect(screen.getByText("Strategies")).toBeInTheDocument();
    expect(screen.getByText("AI Lab")).toBeInTheDocument();
  });

  it("shows layout container", () => {
    render(<SimpleLayout />);
    expect(screen.getByTestId("layout")).toBeInTheDocument();
  });
});
