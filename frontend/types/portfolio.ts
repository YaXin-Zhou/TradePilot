/**
 * 持仓 + 行情相关类型 — N6 前端类型清理
 */

/** Ticker 行情 */
export interface Ticker {
  symbol: string;
  last: number;
  bid?: number;
  ask?: number;
  high?: number;
  low?: number;
  volume?: number;
  timestamp?: number;
  change_pct?: number;
}

/** 单币种余额 */
export interface BalanceEntry {
  free: number;
  used: number;
  total: number;
}

/** 账户余额（按币种索引） */
export type Balance = Record<string, BalanceEntry>;

/** 合约持仓（v2.0 合约版：fetch_positions 口径） */
export interface Position {
  symbol: string;
  side: "long" | "short";
  contracts: number;
  entry_price: number;
  mark_price: number;
  notional_usdt: number;
  unrealized_pnl: number;
  pnl_pct: number;
  leverage: number;
}

/** 持仓概览 */
export interface PortfolioSummary {
  total_usdt: number;
  free_usdt: number;
  positions: Position[];
  total_unrealized_pnl?: number;
}

/** 交易记录 */
export interface Trade {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  amount: number;
  price: number;
  timestamp: number;
  fee?: number;
}

/** 下单结果 */
export interface PlaceOrderResult {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  amount: number;
  price?: number;
  status: string;
  timestamp: number;
  error?: string;
}

/** Pool 策略摘要（pool.tsx 用） */
export interface PoolStrategySummary {
  id: string;
  name: string;
  type: string;
  weight: number;
  sharpe?: number;
  status: string;
}

/** Pool 概要响应 */
export interface PoolSummary {
  strategies: PoolStrategySummary[];
  total_weight: number;
  active_count: number;
}

/** Pool 相关性矩阵 */
export interface PoolCorrelation {
  symbols: string[];
  matrix: number[][];
}
