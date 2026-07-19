const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// Import toast - note: this module is evaluated before React hydrates, use dynamic import in pages
let _toast: any = null;
async function getToast() {
  if (!_toast) {
    try { _toast = await import("react-hot-toast"); } catch {}
  }
  return _toast?.toast;
}

async function request(path: string, options?: RequestInit) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  const json = await res.json();
  if (!json.success) {
    const msg = json.error || "Request failed";
    console.error("API error:", msg);
    getToast().then(t => t?.error?.(msg));
    throw new Error(msg);
  }
  return json.data;
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
  placeLimitOrder: (data: { symbol: string; side: string; amount: number; price: number }) =>
    request("/api/trading/limit-order", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  cancelOrder: (orderId: string, symbol = "BTC/USDT") =>
    request("/api/trading/cancel-order", {
      method: "POST",
      body: JSON.stringify({ order_id: orderId, symbol }),
    }),
  placeMarketOrder: (data: { symbol?: string; side: string; amount: number }) =>
    request("/api/trading/market-order", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Portfolio
  getPortfolioSummary: () => request("/api/portfolio/summary"),
  getTradeHistory: (limit = 100) => request(`/api/portfolio/trades?limit=${limit}`),
  getPerformance: () => request("/api/portfolio/performance"),

  // Strategies
  listStrategies: () => request("/api/strategies/"),
  getStrategy: (id: string) => request(`/api/strategies/${id}`),
  createStrategy: (data: { name: string; type: string; symbol?: string; config?: any }) =>
    request("/api/strategies/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateStrategy: (id: string, data: { status?: string; config?: any }) =>
    request(`/api/strategies/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteStrategy: (id: string) =>
    request(`/api/strategies/${id}`, { method: "DELETE" }),


  // AI Strategy
  aiAnalyze: (data: { api_key: string; strategy_desc: string; symbol?: string; timeframe?: string; auto?: boolean }) =>
    request("/api/ai/analyze", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  testAIConnection: (apiKey: string) =>
    request("/api/ai/test-connection", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    }),
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
  // Backtest
  runBacktest: (data: { strategy: string; symbol?: string; timeframe?: string; limit?: number; capital?: number; params?: any }) =>
    request("/api/backtest/run", { method: "POST", body: JSON.stringify(data) }),
  getBacktestData: (data: { symbol?: string; timeframe?: string; limit?: number }) =>
    request("/api/backtest/data", { method: "POST", body: JSON.stringify(data) }),
  getBacktestHistory: () => request("/api/backtest/history"),
  clearBacktestHistory: () => request("/api/backtest/history/clear", { method: "POST" }),
  // Exchange
  getExchangeStatus: () => request("/api/exchange/status"),
  testConnection: (data: { api_key?: string; secret?: string; passphrase?: string; testnet?: boolean }) =>
    request("/api/exchange/test-connection", { method: "POST", body: JSON.stringify(data) }),
};

