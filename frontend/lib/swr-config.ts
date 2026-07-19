/** SWR 全局配置 — 替换手动 setInterval 轮询 */
import useSWR, { SWRConfiguration } from "swr";
import { api, getToken } from "./api";

/** 默认 SWR 配置 */
export const swrConfig: SWRConfiguration = {
  revalidateOnFocus: true,
  revalidateOnReconnect: true,
  errorRetryCount: 3,
  errorRetryInterval: 5000,
};

/**
 * 通用的 SWR fetcher — 直接调 api 对象方法。
 * 若 requireAuth=true 且当前无 token，则 key 置为 null（SWR 不发请求），
 * 避免未登录时无限轮询需鉴权端点 → 401 → 重定向 → 循环。
 */
export function useMarketData<T>(
  fetcher: () => Promise<T>,
  key: string,
  refreshInterval?: number,
  requireAuth: boolean = false,
) {
  // 需鉴权的端点：无 token 时 key=null，SWR 不发请求
  const effectiveKey = requireAuth && !getToken() ? null : key;
  return useSWR<T>(effectiveKey, fetcher, {
    ...swrConfig,
    refreshInterval: refreshInterval ?? 30000,
    dedupingInterval: 2000,
  });
}

// --- 预定义的 SWR hooks ---

export function useTicker(symbol: string = "BTC/USDT") {
  return useMarketData(() => api.getTicker(symbol), `ticker:${symbol}`);
}

export function useOHLCV(symbol: string = "BTC/USDT", timeframe: string = "1h") {
  return useMarketData(() => api.getOHLCV(symbol, timeframe), `ohlcv:${symbol}:${timeframe}`);
}

export function usePortfolioSummary() {
  return useMarketData(() => api.getPortfolioSummary(), "portfolio:summary", 30000, true);
}

export function useMarketRegime(symbol: string = "BTC/USDT") {
  return useMarketData(() => api.getMarketRegime(symbol), `regime:${symbol}`, 60000);
}

export function useIndicators(symbol: string = "BTC/USDT", timeframe: string = "1h") {
  return useMarketData(() => api.getIndicators(symbol, timeframe), `indicators:${symbol}:${timeframe}`, 60000, true);
}

export function usePrediction(symbol: string = "BTC/USDT") {
  return useMarketData(() => api.getPrediction(symbol), `prediction:${symbol}`, 60000, true);
}

export function useTradeHistory(limit: number = 20) {
  return useMarketData(() => api.getTradeHistory(limit), `trades:${limit}`, 30000, true);
}

export function useExchangeStatus() {
  return useMarketData(() => api.getExchangeStatus(), "exchange:status", 30000);
}

/** Phase 8: 紧急停止状态（5s 轮询，触发了要立刻感知）。
 * 需鉴权：未登录时不轮询，避免 401 循环。 */
export function useKillSwitch() {
  return useMarketData(() => api.getKillSwitchStatus(), "kill-switch", 5000, true);
}
