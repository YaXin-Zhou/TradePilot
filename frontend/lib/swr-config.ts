/** SWR 全局配置 — 替换手动 setInterval 轮询 */
import useSWR, { SWRConfiguration } from "swr";
import { api } from "./api";

/** 默认 SWR 配置 */
export const swrConfig: SWRConfiguration = {
  revalidateOnFocus: true,
  revalidateOnReconnect: true,
  errorRetryCount: 3,
  errorRetryInterval: 5000,
};

/** 通用的 SWR fetcher — 直接调 api 对象方法 */
export function useMarketData<T>(fetcher: () => Promise<T>, key: string, refreshInterval?: number) {
  return useSWR<T>(key, fetcher, {
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
  return useMarketData(() => api.getPortfolioSummary(), "portfolio:summary");
}

export function useMarketRegime(symbol: string = "BTC/USDT") {
  return useMarketData(() => api.getMarketRegime(symbol), `regime:${symbol}`, 60000);
}

export function useIndicators(symbol: string = "BTC/USDT", timeframe: string = "1h") {
  return useMarketData(() => api.getIndicators(symbol, timeframe), `indicators:${symbol}:${timeframe}`, 60000);
}

export function usePrediction(symbol: string = "BTC/USDT") {
  return useMarketData(() => api.getPrediction(symbol), `prediction:${symbol}`, 60000);
}

export function useTradeHistory(limit: number = 20) {
  return useMarketData(() => api.getTradeHistory(limit), `trades:${limit}`);
}

export function useExchangeStatus() {
  return useMarketData(() => api.getExchangeStatus(), "exchange:status", 30000);
}
