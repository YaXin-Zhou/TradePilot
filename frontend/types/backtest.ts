/**
 * 回测相关类型 — N6 前端类型清理
 *
 * 与后端 backend/api/backtest.py 的 BacktestParams 对齐。
 */

/** 回测参数 */
export interface BacktestParams {
  strategy_type: string;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  params: Record<string, unknown>;
}

/** 回测指标 */
export interface BacktestMetrics {
  total_return_pct: number;
  sharpe: number;
  max_drawdown_pct: number;
  win_rate: number;
  total_trades: number;
  profit_factor: number;
  dsa?: number; // Deflated Sharpe Ratio
  pbo?: number; // Probability of Backtest Overfitting
}

/** 回测交易记录 */
export interface BacktestTrade {
  timestamp: number;
  side: "buy" | "sell";
  price: number;
  amount: number;
  pnl?: number;
}

/** 回测结果 */
export interface BacktestResult {
  metrics: BacktestMetrics;
  trades: BacktestTrade[];
  equity_curve: Array<{ timestamp: number; equity: number }>;
  scientific_passed?: boolean;
}

/** MetricCard 组件 props（替代原 `: any`） */
export interface MetricCardProps {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: string | number;
  color?: string;
  suffix?: string;
}

/** formatTime 函数参数（替代原 `ts: any`） */
export type Timestamp = number | string | Date | null | undefined;
