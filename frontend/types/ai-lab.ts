/**
 * AI 实验室相关类型 — N6 前端类型清理
 *
 * 与后端 backend/services/ai_iterator.py / backend/api/ai_strategy.py 对齐。
 */

/** 迭代任务状态 */
export type IterationStatus =
  | "pending"
  | "running"
  | "generating"
  | "backtesting"
  | "completed"
  | "converged"
  | "done"
  | "failed";

/** 迭代任务概要（列表项） */
export interface IterationTaskSummary {
  task_id: string;
  goal: string;
  symbol: string;
  timeframe?: string;
  status: IterationStatus;
  created_at: string;
  best_score?: number;
  rounds_count?: number;
  current_round?: number;
  max_rounds?: number;
  total_variants?: number;
  converged?: boolean;
}

/** 变体性能指标 */
export interface VariantMetrics {
  sharpe_is?: number;
  sharpe_oos?: number;
  total_return_pct?: number;
  max_drawdown_pct?: number;
  pbo?: number;
  dsr?: number;
  score?: number;
  win_rate?: number;
  total_trades?: number;
  scientific_passed?: boolean;
}

/** 单个变体（策略 + 性能） */
export interface IterationVariant extends VariantMetrics {
  variant_id: string;
  strategy_type: string;
  params: Record<string, unknown>;
  rationale?: string;
}

/** 迭代轮次 */
export interface IterationRound {
  round: number;
  round_number?: number;
  status?: IterationStatus;
  variants: IterationVariant[];
  best_variant?: IterationVariant;
  top_score?: number;
  top_sharpe_oos?: number;
}

/** 迭代任务详情（含轮次和最佳变体） */
export interface IterationTaskDetail extends IterationTaskSummary {
  variants_generated: number;
  rounds: IterationRound[];
  best_variant?: IterationVariant;
  max_rounds: number;
  max_drawdown: number;
  min_sharpe: number;
  progress_pct?: number;
  scientific_passed?: boolean | number;
  convergence_reason?: string;
  error?: string;
}

/** 启动迭代请求 */
export interface StartIterationRequest {
  goal: string;
  symbol: string;
  timeframe: string;
  variants: number;
  max_rounds: number;
  max_drawdown: number;
  min_sharpe: number;
  max_concentration: number;
}
