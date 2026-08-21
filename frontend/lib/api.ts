export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8090";

// Import toast - note: this module is evaluated before React hydrates, use dynamic import in pages
type ToastModule = typeof import("react-hot-toast");
let _toast: ToastModule | null = null;
async function getToast() {
  if (!_toast) {
    try { _toast = await import("react-hot-toast"); } catch {}
  }
  return _toast?.toast;
}

// 防止 401 时重复跳转 /login（多个并发请求同时收到 401 会触发多次跳转 → 闪烁）
let _isRedirectingToLogin = false;

async function request(path: string, options?: RequestInit, timeoutMs: number = 15000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const mergedOpts = { ...options, signal: options?.signal || controller.signal };
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(options?.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { headers, ...mergedOpts });
  clearTimeout(timeoutId);
  if (res.status === 401) {
    clearToken();
    // 仅在浏览器环境、且当前不在 /login 页面时跳转，避免 login 页面无限重载
    if (typeof window !== "undefined" && !_isRedirectingToLogin) {
      const onLogin = window.location.pathname === "/login";
      if (!onLogin) {
        _isRedirectingToLogin = true;
        window.location.href = "/login";
      }
    }
    throw new Error("Unauthorized");
  }
  clearTimeout(timeoutId);
  const json = await res.json();
  if (!json.success) {
    const msg = json.error || "Request failed";
    console.error("API error:", msg);
    getToast().then(t => t?.error?.(msg));
    throw new Error(msg);
  }
  return json.data;
}

// Auth token helpers
// v2.1: 本地部署免登录 — getToken 始终返回占位 token（后端已禁用鉴权），
// 使 SWR 的 requireAuth 门禁放行请求。
export function getToken(): string | null {
  return "local-dev-token";
}
export function setToken(token: string) {
  // 免登录：保留签名，不再写 localStorage
}
export function clearToken() {
  // 免登录：保留签名，不再清除
}

export const api = {
  // Market
  getTicker: (symbol = "BTC/USDT") =>
    request(`/api/market/ticker?symbol=${encodeURIComponent(symbol)}`),
  getOHLCV: (symbol = "BTC/USDT", timeframe = "1h", limit = 200) =>
    request(`/api/market/ohlcv?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`),
  getOrderbook: (symbol = "BTC/USDT", limit = 20) =>
    request(`/api/market/orderbook?symbol=${encodeURIComponent(symbol)}&limit=${limit}`),

  // Trading
  getBalance: () => request("/api/trading/balance"),
  getOpenOrders: (symbol = "BTC/USDT") =>
    request(`/api/trading/open-orders?symbol=${encodeURIComponent(symbol)}`),
  placeLimitOrder: (data: { symbol: string; side: string; amount: number; price: number; confirm_live?: boolean }) =>
    request("/api/trading/limit-order", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  cancelOrder: (orderId: string, symbol = "BTC/USDT") =>
    request("/api/trading/cancel-order", {
      method: "POST",
      body: JSON.stringify({ order_id: orderId, symbol }),
    }),
  cancelAllOrders: (symbol = "") =>
    request(`/api/trading/cancel-all?symbol=${encodeURIComponent(symbol)}`, { method: "POST" }),
  placeMarketOrder: (data: { symbol?: string; side: string; amount: number; confirm_live?: boolean }) =>
    request("/api/trading/market-order", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Phase 8: 紧急停止（Kill Switch）

  getKillSwitchStatus: () => request("/api/trading/kill-switch"),
  emergencyStop: (reason = "", confirm = false) =>
    request("/api/trading/emergency-stop", {
      method: "POST",
      body: JSON.stringify({ reason, confirm }),
    }),
  emergencyReset: (confirm = false) =>
    request("/api/trading/emergency-reset", {
      method: "POST",
      body: JSON.stringify({ confirm }),
    }),

  // Manual Risk Settings
  getManualRiskSettings: () => request("/api/trading/manual-risk-settings"),
  updateManualRiskSettings: (data: Record<string, unknown>) =>
    request("/api/trading/manual-risk-settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Portfolio
  getPortfolioSummary: () => request("/api/portfolio/summary"),
  getTradeHistory: (limit = 100) => request(`/api/portfolio/trades?limit=${limit}`),
  getPerformance: () => request("/api/portfolio/performance"),
  getPositions: () => request("/api/portfolio/positions"),
  getRealtimeAssets: () => request("/api/portfolio/realtime"),
  closePosition: (asset: string, confirm: boolean = false) =>
    request("/api/portfolio/close", { method: "POST", body: JSON.stringify({ asset, confirm }) }),

  // Strategies
  listStrategies: () => request("/api/strategies/"),
  getStrategy: (id: string) => request(`/api/strategies/${id}`),
  createStrategy: (data: { name: string; type: string; symbol?: string; config?: Record<string, unknown> }) =>
    request("/api/strategies/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateStrategy: (id: string, data: { status?: string; config?: Record<string, unknown> }) =>
    request(`/api/strategies/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  startStrategy: (id: string) =>
    request(`/api/strategies/${id}/start`, { method: "POST" }),
  stopStrategy: (id: string) =>
    request(`/api/strategies/${id}/stop`, { method: "POST" }),
  deleteStrategy: (id: string) =>
    request(`/api/strategies/${id}`, { method: "DELETE" }),
  getStrategyLogs: (id: string, limit = 100) =>
    request(`/api/strategies/${id}/logs?limit=${limit}`),
  batchDeleteStrategies: (ids: string[], confirm = false) =>
    request("/api/strategies/warehouse/batch-delete", {
      method: "POST",
      body: JSON.stringify({ strategy_ids: ids, confirm }),
    }),
  autoCleanupWarehouse: () =>
    request("/api/strategies/warehouse/cleanup", { method: "POST" }),


  // AI Strategy — 超时增加到 120s（需调用 DeepSeek + 回测验证）
  aiAnalyze: (data: { strategy_desc: string; symbol?: string; timeframe?: string; auto?: boolean }) =>
    request("/api/ai/analyze", {
      method: "POST",
      body: JSON.stringify(data),
    }, 120000),
  testAIConnection: () =>
    request("/api/ai/test-connection", {
      method: "POST",
      body: JSON.stringify({}),
    }, 30000),
  // Analysis
  getIndicators: (symbol = "BTC/USDT", timeframe = "1h") =>
    request(`/api/analysis/indicators?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`),
  getPrediction: (symbol = "BTC/USDT", timeframe = "1h") =>
    request(`/api/analysis/predict?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`),
  trainModel: (symbol = "BTC/USDT", timeframe = "1h", limit = 1000) =>
    request(`/api/analysis/train?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`, {
      method: "POST",
    }),
  getMarketRegime: (symbol = "BTC/USDT", timeframe = "1h") =>
    request(`/api/analysis/market-regime?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`),
  getAdaptiveState: (symbol = "BTC/USDT") =>
    request(`/api/analysis/adaptive?symbol=${encodeURIComponent(symbol)}`),
  // Risk Engine
  getRiskPolicies: () => request("/api/analysis/risk-policies"),
  updateRiskPolicy: (data: {
    regime: string;
    max_position_pct?: number;
    max_single_strategy_pct?: number;
    max_daily_loss_pct?: number;
    stop_loss_pct?: number;
    trailing_stop_pct?: number;
    min_sharpe_entry?: number;
    max_correlation?: number;
    time_stop_hours?: number;
    atr_stop_multiplier?: number;
    allowed_strategies?: string[];
  }) => request("/api/analysis/risk-policies", { method: "POST", body: JSON.stringify(data) }),
  resetRiskPolicies: () => request("/api/analysis/risk-policies/reset", { method: "POST" }),
  checkRisk: (data: {
    regime: string;
    strategy_type: string;
    sharpe_oos: number;
    total_capital: number;
    current_position?: number;
    new_amount?: number;
    strategy_position?: number;
    daily_pnl?: number;
  }) => request("/api/analysis/risk-check", { method: "POST", body: JSON.stringify(data) }),
  // Backtest
  runBacktest: (data: { strategy: string; symbol?: string; timeframe?: string; limit?: number; capital?: number; position_size?: number; trading_fee?: number; slippage?: number; params?: Record<string, unknown> }) =>
    request("/api/backtest/run", { method: "POST", body: JSON.stringify(data) }, 120000), // 120s for full validation
  runBacktestAsync: (data: { strategy: string; symbol?: string; timeframe?: string; limit?: number; capital?: number; position_size?: number; trading_fee?: number; slippage?: number; params?: Record<string, unknown> }) =>
    request("/api/backtest/async", { method: "POST", body: JSON.stringify(data) }),
  getBacktestStatus: (taskId: string) =>
    request(`/api/backtest/async/${taskId}`),
  getBacktestData: (data: { symbol?: string; timeframe?: string; limit?: number }) =>
    request("/api/backtest/data", { method: "POST", body: JSON.stringify(data) }),
  getBacktestHistory: () => request("/api/backtest/history"),
  clearBacktestHistory: () => request("/api/backtest/history/clear", { method: "POST" }),
  getBacktestStats: () => request("/api/backtest/stats"),

  // AI Iteration — 超时 60s
  startIteration: (data: { goal: string; symbol?: string; timeframe?: string; variants?: number; max_rounds?: number; capital?: number; risk_constraints?: Record<string, unknown> }) =>
    request("/api/ai/iterate", { method: "POST", body: JSON.stringify(data) }, 60000),
  getIterationStatus: (taskId: string) =>
    request(`/api/ai/iterate/status/${taskId}`, undefined, 15000),
  getIterationBest: (taskId: string) =>
    request(`/api/ai/iterate/best/${taskId}`, undefined, 15000),
  listIterationTasks: (limit = 20) =>
    request(`/api/ai/iterate/tasks?limit=${limit}`, undefined, 15000),
  saveIterationToWarehouse: (data: { strategy_type: string; params: Record<string, unknown>; symbol: string; metrics: Record<string, unknown> }) =>
    request("/api/ai/iterate/save-to-warehouse", { method: "POST", body: JSON.stringify(data) }),
  // Settings (双套配置：模拟盘 + 实盘)
  getExchangeSettings: () => request("/api/settings/exchange"),
  saveExchangeSettings: (data: { mode: "testnet" | "live"; api_key: string; secret: string; passphrase: string; verify_permissions?: boolean }) =>
    request("/api/settings/exchange", { method: "POST", body: JSON.stringify(data) }),
  switchExchangeMode: (data: { mode: "testnet" | "live"; confirm?: boolean }) =>
    request("/api/settings/exchange/switch", { method: "POST", body: JSON.stringify(data) }),
  testConnection: (data: { mode: "testnet" | "live"; api_key?: string; secret?: string; passphrase?: string }) =>
    request("/api/settings/exchange/test", { method: "POST", body: JSON.stringify(data) }),

  // Settings - DeepSeek API Key
  getDeepSeekSettings: () => request("/api/settings/deepseek"),
  saveDeepSeekSettings: (data: { api_key: string }) =>
    request("/api/settings/deepseek", { method: "POST", body: JSON.stringify(data) }),
  testDeepSeekConnection: (data: { api_key: string }) =>
    request("/api/settings/deepseek/test", { method: "POST", body: JSON.stringify(data) }),

  // Exchange
  getExchangeStatus: () => request("/api/exchange/status"),

  // Strategy Pool
  getPoolSummary: () => request("/api/strategies/pool/summary"),
  getPoolCorrelation: () => request("/api/strategies/pool/correlation"),
  registerToPool: (strategyId: string, data: { name: string; strategy_type: string; weight?: number }) =>
    request(`/api/strategies/pool/${strategyId}/register`, { method: "POST", body: JSON.stringify(data) }),
  setPoolStatus: (strategyId: string, status: string) =>
    request(`/api/strategies/pool/${strategyId}/status?status=${status}`, { method: "POST" }),
  removeFromPool: (strategyId: string) =>
    request(`/api/strategies/pool/${strategyId}`, { method: "DELETE" }),
  updateLearner: (data: { returns: Record<string, number>; sleeping?: string[]; regime?: string }) =>
    request("/api/strategies/learner/update", { method: "POST", body: JSON.stringify(data) }),
  getLearnerWeights: () => request("/api/strategies/learner/weights"),
  allocateCapital: (data: { weights: Record<string, number>; total_capital: number; current_positions?: Record<string, number>; regime?: string }) =>
    request("/api/portfolio/allocate", { method: "POST", body: JSON.stringify(data) }),
  rebalanceCapital: (data: { weights: Record<string, number>; total_capital: number; current_positions?: Record<string, number>; regime?: string }) =>
    request("/api/portfolio/rebalance", { method: "POST", body: JSON.stringify(data) }),

  // Weak Signal Matrix
  getWeakSignals: (symbol = "BTC/USDT", timeframe = "1h") =>
    request(`/api/analysis/weak-signals?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`),
  getFeatureNames: () => request("/api/analysis/feature-names"),
  getFearGreed: () => request("/api/analysis/fear-greed"),
  getOpenInterest: (symbol = "BTC/USDT") =>
    request(`/api/analysis/open-interest?symbol=${encodeURIComponent(symbol)}`),

  // News Sentiment
  getNewsSentiment: (symbol = "BTC/USDT", limit = 20) =>
    request(`/api/analysis/news-sentiment?symbol=${encodeURIComponent(symbol)}&limit=${limit}`),

  // AI Heartbeat
  runHeartbeat: () => request("/api/strategies/heartbeat/run", { method: "POST" }),
  getHeartbeatHistory: (limit = 10) =>
    request(`/api/strategies/heartbeat/history?limit=${limit}`),
  getHeartbeatLast: () => request("/api/strategies/heartbeat/last"),

  // Auth
  login: (username: string, password: string) =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  register: (username: string, password: string, email?: string) =>
    request("/api/auth/register", { method: "POST", body: JSON.stringify({ username, password, email }) }),
};



