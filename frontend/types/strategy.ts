/**
 * 策略相关类型 — N6 前端类型清理
 *
 * 与后端 backend/db/models.py StrategyType 枚举对齐。
 */

/** 策略类型（与后端 StrategyType 枚举一致） */
export type StrategyType =
  | "GRID"
  | "SMA_CROSS"
  | "MA_CROSS"
  | "RSI"
  | "BOLLINGER"
  | "ML_SIGNAL"
  | "CUSTOM"
  | "AI_GENERATED";

/** 策略状态 */
export type StrategyStatus = "RUNNING" | "STOPPED" | "PAUSED" | "ERROR";

/** 策略对象（与后端 Strategy 表对齐） */
export interface Strategy {
  id: number;
  name: string;
  type: StrategyType;
  symbol: string;
  status: StrategyStatus;
  config: Record<string, unknown>;
  created_at: string;
  updated_at?: string;
}

/** 策略配置（grid/ma_cross 等不同类型有不同字段） */
export interface BaseStrategyConfig {
  symbol: string;
  timeframe?: string;
  [key: string]: unknown;
}

/** Grid 策略配置 */
export interface GridConfig extends BaseStrategyConfig {
  lower_price: number;
  upper_price: number;
  grid_count: number;
  order_amount: number;
}

/** MA Cross 策略配置 */
export interface MaCrossConfig extends BaseStrategyConfig {
  fast_period: number;
  slow_period: number;
  order_amount: number;
}

/** AI 策略分析请求 */
export interface AiAnalyzeRequest {
  strategy_desc: string;
  auto: boolean;
}

/** AI 策略分析响应 */
export interface AiAnalyzeResult {
  strategy_type?: StrategyType;
  params?: Record<string, unknown>;
  strategy_params?: Record<string, unknown>;
  rationale?: string;
  reason?: string;
  expected_performance?: {
    sharpe?: number;
    return_pct?: number;
    max_drawdown_pct?: number;
  };
  signal?: string;
  confidence?: number;
  current_price?: number;
  indicators?: Record<string, number | string>;
  strategy_description?: string;
  market_assessment?: string;
  backtest?: {
    total_return_pct?: number;
    sharpe_ratio?: number;
    max_drawdown_pct?: number;
    win_rate?: number;
    total_trades?: number;
    profit_factor?: number;
  };
  /** 自动入库后的策略 ID */
  strategy_id?: string;
  /** 是否已注册到策略池 */
  pool_registered?: boolean;
  /** 过拟合验证结果 */
  validation?: {
    sharpe_oos?: number;
    pbo?: number;
    dsr?: number;
    scientific_passed?: boolean;
  };
  /** 是否通过科学验证（PBO≤0.5 且 OOS夏普>0） */
  scientific_valid?: boolean;
  /** 是否因为验证未通过而跳过自动入库 */
  auto_save_skipped?: boolean;
  error?: string;
}
