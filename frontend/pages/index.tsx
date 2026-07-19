import { useState, useEffect } from "react";
import PortfolioSummary from "../components/PortfolioSummary";
import PriceChart from "../components/PriceChart";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import { useRealtime } from "../lib/useRealtime";
import {
  TrendingUp, TrendingDown, Activity, Brain, RefreshCw,
  ArrowUpRight, ArrowDownRight, Minus
} from "lucide-react";

export default function Dashboard() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [ticker, setTicker] = useState<any>(null);
  const [regime, setRegime] = useState<any>(null);
  const [prediction, setPrediction] = useState<any>(null);
  const [indicators, setIndicators] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [ohlcv, setOhlcv] = useState<any[]>([]);
  const { t } = useLanguage();
  useRealtime({ onTicker: setTicker });

  useEffect(() => {
    api.getMarketRegime().then(setRegime).catch(() => {});
    api.getIndicators().then(setIndicators).catch(() => {});
    api.getPrediction().then(setPrediction).catch(() => {});
    api.getTradeHistory(20).then(setTrades).catch(() => {});
    api.getOHLCV().then(setOhlcv).catch(() => {});
  }, [refreshKey]);

  const signalBadge = (signal: string) => {
    if (signal === "buy") return <span className="flex items-center gap-1 text-xs font-medium text-green"><ArrowUpRight size={14} /> BUY</span>;
    if (signal === "sell") return <span className="flex items-center gap-1 text-xs font-medium text-red"><ArrowDownRight size={14} /> SELL</span>;
    return <span className="flex items-center gap-1 text-xs font-medium text-dark-400"><Minus size={14} /> HOLD</span>;
  };

  useEffect(() => {
    const interval = setInterval(() => setRefreshKey(k => k + 1), 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">{t("dash.overview")}</h2>
          <p className="text-xs text-dark-400 mt-1">{t("dash.overviewSub")}</p>
        </div>
        <button
          onClick={() => setRefreshKey((k) => k + 1)}
          className="btn-ghost flex items-center gap-2 text-xs"
        >
          <RefreshCw size={14} /> {t("dash.refresh")}
        </button>
      </div>

      <PortfolioSummary refreshKey={refreshKey} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
            <PriceChart refreshKey={refreshKey} ticker={ticker} />
            </div>
        </div>

        <div className="space-y-4">
          {/* Market Regime */}
          <div className="card">
            <div className="flex items-center gap-2 mb-3">
              <Activity size={16} className="text-okx-yellow" />
              <span className="text-sm font-semibold text-white">{t("dash.marketRegime")}</span>
            </div>
            {regime ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-400">{t("dash.regime")}</span>
                  <span className={`text-sm font-semibold ${
                    regime.regime === "bull" ? "text-green" : regime.regime === "bear" ? "text-red" : "text-okx-yellow"
                  }`}>
                    {t(`enum.${regime.regime}`).toUpperCase()}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-400">{t("dash.volatility")}</span>
                  <span className="text-xs text-dark-200">{t(`enum.${regime.volatility}`).toUpperCase()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-400">{t("dash.rsi")}</span>
                  <span className={`text-xs font-mono ${
                    (regime.rsi || 0) > 70 ? "text-red" : (regime.rsi || 0) < 30 ? "text-green" : "text-dark-200"
                  }`}>
                    {regime.rsi?.toFixed(1)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-400">{t("dash.vsSma20")}</span>
                  <span className={`text-xs font-mono ${(regime.price_vs_sma20 || 0) >= 0 ? "text-green" : "text-red"}`}>
                    {regime.price_vs_sma20?.toFixed(2)}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-400">{t("dash.vsSma50")}</span>
                  <span className={`text-xs font-mono ${(regime.price_vs_sma50 || 0) >= 0 ? "text-green" : "text-red"}`}>
                    {regime.price_vs_sma50?.toFixed(2)}%
                  </span>
                </div>
              </div>
            ) : (
              <div className="h-20 flex items-center justify-center">
                <span className="text-xs text-dark-500">{t("dash.loading")}</span>
              </div>
            )}
          </div>

          {/* ML Prediction */}
          <div className="card">
            <div className="flex items-center gap-2 mb-3">
              <Brain size={16} className="text-purple-400" />
              <span className="text-sm font-semibold text-white">{t("dash.aiSignal")}</span>
            </div>
            {prediction ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-400">{t("dash.signal")}</span>
                  {signalBadge(prediction.signal)}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-400">{t("dash.confidence")}</span>
                  <span className="text-xs font-mono text-dark-200">
                    {(prediction.confidence * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-dark-800 rounded-full h-1.5">
                  <div
                    className="h-1.5 rounded-full transition-all"
                    style={{
                      width: `${(prediction.confidence * 100).toFixed(0)}%`,
                      background: prediction.signal === "buy" ? "#00c076" : prediction.signal === "sell" ? "#f6465d" : "#848e9c",
                    }}
                  />
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-green">{t("dash.upProb")}: {(prediction.prob_up * 100).toFixed(1)}%</span>
                  <span className="text-red">{t("dash.downProb")}: {(prediction.prob_down * 100).toFixed(1)}%</span>
                </div>
              </div>
            ) : (
              <div className="h-20 flex items-center justify-center">
                <span className="text-xs text-dark-500">{t("dash.trainFirst")}</span>
              </div>
            )}
          </div>

          {indicators && (
            <div className="card">
              <div className="flex items-center gap-2 mb-3">
                <Activity size={16} className="text-okx-blue" />
                <span className="text-sm font-semibold text-white">{t("dash.indicators")}</span>
              </div>
              <div className="space-y-2 text-xs">
                {[
                  { label: "RSI", key: "rsi", color: (indicators.rsi || 0) > 70 ? "text-red" : (indicators.rsi || 0) < 30 ? "text-green" : "text-dark-200" },
                  { label: "MACD", key: "macd", color: (indicators.macd || 0) >= 0 ? "text-green" : "text-red" },
                  { label: "MACD Signal", key: "macd_signal", color: "text-dark-200" },
                  { label: "BB Upper", key: "bb_upper", color: "text-dark-200" },
                  { label: "BB Lower", key: "bb_lower", color: "text-dark-200" },
                  { label: "BB Width", key: "bb_width", color: "text-dark-200" },
                  { label: "EMA 9", key: "ema_9", color: "text-okx-blue" },
                  { label: "EMA 21", key: "ema_21", color: "text-okx-yellow" },
                  { label: "ATR", key: "atr", color: "text-dark-200" },
                  { label: "Vol Ratio", key: "volume_ratio", color: (indicators.volume_ratio || 0) > 1.5 ? "text-green" : "text-dark-200" },
                ].map((item) => (
                  <div key={item.label} className="flex justify-between py-1 border-b border-dark-800/50 last:border-0">
                    <span className="text-dark-400">{item.label}</span>
                    <span className={`font-mono ${item.color}`}>
                      {typeof indicators[item.key] === "number" ? indicators[item.key]?.toFixed?.(2) ?? indicators[item.key] : indicators[item.key]}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

      {/* Recent Trades */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold text-white">{t("dash.recentTrades")}</span>
          <span className="text-xs text-dark-400">{trades.length} {t("dash.records")}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-dark-400 border-b border-dark-800">
                <th className="text-left py-2 pr-4">{t("dash.pair")}</th>
                <th className="text-right px-2 py-2">{t("dash.buyPrice")}</th>
                <th className="text-right px-2 py-2">{t("dash.sellPrice")}</th>
                <th className="text-right px-2 py-2">{t("dash.quantity")}</th>
                <th className="text-right px-2 py-2">{t("dash.profit")}</th>
                <th className="text-right px-2 py-2">{t("dash.pnlPct")}</th>
                <th className="text-right pl-2 py-2">{t("dash.time")}</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-dark-500">
                    {t("dash.noTrades")}
                  </td>
                </tr>
              )}
              {trades.slice(0, 10).map((t) => (
                <tr key={t.id} className="border-b border-dark-800/50 hover:bg-dark-800/30">
                  <td className="py-2.5 pr-4 font-medium text-dark-200">{t.symbol}</td>
                  <td className="text-right px-2 py-2 font-mono">${t.buy_price?.toFixed(2)}</td>
                  <td className="text-right px-2 py-2 font-mono">${t.sell_price?.toFixed(2)}</td>
                  <td className="text-right px-2 py-2 font-mono">{t.quantity?.toFixed(6)}</td>
                  <td className={`text-right px-2 py-2 font-mono ${(t.profit || 0) >= 0 ? "text-green" : "text-red"}`}>
                    {(t.profit || 0) >= 0 ? "+" : ""}{t.profit?.toFixed(4)}
                  </td>
                  <td className={`text-right px-2 py-2 font-mono ${(t.profit_pct || 0) >= 0 ? "text-green" : "text-red"}`}>
                    {(t.profit_pct || 0) >= 0 ? "+" : ""}{t.profit_pct?.toFixed(2)}%
                  </td>
                  <td className="text-right pl-2 py-2 text-dark-400">
                    {t.closed_at ? new Date(t.closed_at).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
        </div>
    </div>
  );
}