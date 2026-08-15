// v2.0: 真实 Skeleton 组件测试（替换旧的假 StrategyCard 测试）
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import Skeleton, { DashboardSkeleton, TradingSkeleton, BacktestSkeleton } from "../../components/Skeleton";

describe("Skeleton（真实组件）", () => {
  it("默认骨架屏渲染", () => {
    const { container } = render(<Skeleton />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("DashboardSkeleton 渲染多个卡片占位", () => {
    const { container } = render(<DashboardSkeleton />);
    const pulses = container.querySelectorAll(".animate-pulse");
    expect(pulses.length).toBeGreaterThanOrEqual(4);
  });

  it("TradingSkeleton 与 BacktestSkeleton 正常渲染不崩溃", () => {
    render(<TradingSkeleton />);
    render(<BacktestSkeleton />);
    expect(document.body).toBeTruthy();
  });
});
