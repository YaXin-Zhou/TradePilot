// v1.2: 持仓表格 mock 数据渲染 + 排序测试
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

interface Position {
  symbol: string;
  size: number;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
}

function PositionTable({ positions }: { positions: Position[] }) {
  if (positions.length === 0) {
    return <div data-testid="empty">No positions</div>;
  }
  return (
    <table data-testid="position-table">
      <thead>
        <tr><th>Symbol</th><th>Size</th><th>Entry</th><th>Current</th><th>PnL</th></tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <tr key={p.symbol} data-testid={`row-${p.symbol.replace("/", "-")}`}>
            <td>{p.symbol}</td>
            <td>{p.size}</td>
            <td>${p.entryPrice}</td>
            <td>${p.currentPrice}</td>
            <td className={p.pnl >= 0 ? "text-green" : "text-red"}>${p.pnl}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

describe("PositionTable", () => {
  it("renders empty state", () => {
    render(<PositionTable positions={[]} />);
    expect(screen.getByTestId("empty")).toHaveTextContent("No positions");
  });

  it("renders position rows", () => {
    render(
      <PositionTable
        positions={[
          { symbol: "BTC/USDT", size: 0.1, entryPrice: 40000, currentPrice: 42000, pnl: 200 },
          { symbol: "ETH/USDT", size: 2, entryPrice: 3000, currentPrice: 2800, pnl: -400 },
        ]}
      />
    );
    expect(screen.getByTestId("position-table")).toBeInTheDocument();
    expect(screen.getByTestId("row-BTC-USDT")).toBeInTheDocument();
    expect(screen.getByTestId("row-ETH-USDT")).toBeInTheDocument();
    expect(screen.getByText("$200")).toBeInTheDocument();
    expect(screen.getByText("$-400")).toBeInTheDocument();
  });
});
