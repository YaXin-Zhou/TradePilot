/** 全局应用状态 — Zustand */
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AppState {
  /** 当前选中的交易对 */
  currentSymbol: string;
  setCurrentSymbol: (symbol: string) => void;

  /** 交易所连接状态 */
  exchangeConnected: boolean;
  exchangeTestnet: boolean;
  setExchangeStatus: (connected: boolean, testnet: boolean) => void;

  /** 用户偏好 */
  theme: "dark" | "light";
  dashboardAutoRefresh: boolean;
  setTheme: (theme: "dark" | "light") => void;
  setAutoRefresh: (enabled: boolean) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      currentSymbol: "BTC/USDT",
      setCurrentSymbol: (symbol) => set({ currentSymbol: symbol }),

      exchangeConnected: false,
      exchangeTestnet: true,
      setExchangeStatus: (connected, testnet) =>
        set({ exchangeConnected: connected, exchangeTestnet: testnet }),

      theme: "dark",
      dashboardAutoRefresh: true,
      setTheme: (theme) => set({ theme }),
      setAutoRefresh: (enabled) => set({ dashboardAutoRefresh: enabled }),
    }),
    {
      name: "ai-quant-prefs",
      partialize: (state) => ({
        currentSymbol: state.currentSymbol,
        theme: state.theme,
        dashboardAutoRefresh: state.dashboardAutoRefresh,
      }),
    }
  )
);
