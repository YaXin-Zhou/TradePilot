// v1.2: 策略卡片组件测试
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

interface StrategyCardProps {
  name: string;
  type: string;
  symbol: string;
  status: string;
}

function StrategyCard({ name, type, symbol, status }: StrategyCardProps) {
  return (
    <div data-testid="strategy-card">
      <h3>{name}</h3>
      <span data-testid="type">{type}</span>
      <span data-testid="symbol">{symbol}</span>
      <span data-testid="status">{status}</span>
    </div>
  );
}

describe("StrategyCard", () => {
  it("renders strategy details", () => {
    render(
      <StrategyCard
        name="MA Cross BTC"
        type="MA_CROSS"
        symbol="BTC/USDT"
        status="RUNNING"
      />
    );
    expect(screen.getByText("MA Cross BTC")).toBeInTheDocument();
    expect(screen.getByTestId("type")).toHaveTextContent("MA_CROSS");
    expect(screen.getByTestId("symbol")).toHaveTextContent("BTC/USDT");
    expect(screen.getByTestId("status")).toHaveTextContent("RUNNING");
  });

  it("handles stopped status", () => {
    render(
      <StrategyCard
        name="Grid ETH"
        type="GRID"
        symbol="ETH/USDT"
        status="STOPPED"
      />
    );
    expect(screen.getByTestId("status")).toHaveTextContent("STOPPED");
  });
});
