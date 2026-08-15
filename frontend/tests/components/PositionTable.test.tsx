// v2.0: 真实 ErrorBoundary 组件测试（替换旧的假 PositionTable 测试）
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ErrorBoundary from "../../components/ErrorBoundary";

function Bomb(): React.ReactElement {
  throw new Error("测试错误");
}

describe("ErrorBoundary（真实组件）", () => {
  it("正常渲染子内容", () => {
    render(<ErrorBoundary><div data-testid="child">正常内容</div></ErrorBoundary>);
    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.getByText("正常内容")).toBeInTheDocument();
  });

  it("捕获子组件错误并显示降级 UI", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBoundary><Bomb /></ErrorBoundary>);
    expect(screen.getByText("系统出了点问题")).toBeInTheDocument();
    expect(screen.getByText("测试错误")).toBeInTheDocument();
    expect(screen.getByText("重新加载")).toBeInTheDocument();
    spy.mockRestore();
  });
});
