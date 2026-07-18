const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request(path: string, options?: RequestInit) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  const json = await res.json();
  if (!json.success) { console.error('API error:', json.error); throw new Error(json.error || 'request failed'); }
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
  aiAnalyze: (data: { api_key: string; strategy_desc: string; symbol?: string; timeframe?: string }) =>
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
};
