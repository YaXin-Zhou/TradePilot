import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import { RefreshCw, Activity, SlidersHorizontal, ShieldCheck, Brain } from "lucide-react";

/**
 * AI 自适应面板 — v6 问题2：把「AI 三件事」可视化
 *   1. regime 识别（趋势/震荡 × 高/低波动 → 动量/波动率因子）
 *   2. 权重自适应（策略类型 × regime 乘数 → 有效权重）
 *   3. 风控（当前 regime 的仓位/止损/日亏/入场门槛）
 */

const REGIME_ZH: Record<string, string> = {
  TRENDING_UP: "趋势上涨",
  TRENDING_DOWN: "趋势下跌",
  RANGING_HIGH_VOL: "震荡·高波动",
  RANGING_LOW_VOL: "震荡·低波动",
};

export default function AdaptivePanel({ symbol = "BTC/USDT" }: { symbol?: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { lang } = useLanguage();
  const isZh = lang === "zh";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.getAdaptiveState(symbol);
      setData(d);
    } catch {}
    setLoading(false);
  }, [symbol]);

  useEffect(() => { load(); }, [load]);

  const regime = data?.regime;
  const weights = data?.weights ?? [];
  const policy = data?.risk_policy;

  return (
    <div className="card border-indigo-500/20">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Brain size={16} className="text-indigo-400" />
          <span className="text-sm font-semibold text-white">{isZh ? "AI 自适应状态" : "AI Adaptive State"}</span>
        </div>
        <button onClick={load} className="btn-ghost text-xs py-1 px-2">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {loading && <p className="text-xs text-dark-400 text-center py-6">{isZh ? "加载中..." : "Loading..."}</p>}

      {!loading && data && (
        <div className="space-y-4">
          {/* 1. Regime 识别 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Activity size={13} className="text-okx-green" />
              <span className="text-xs font-semibold text-dark-200">{isZh ? "1. Regime 识别" : "1. Regime Detection"}</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              <MiniStat label={isZh ? "市场状态" : "Regime"}
                value={isZh ? (REGIME_ZH[regime?.regime] || regime?.regime) : regime?.regime}
                color="#a855f7" />
              <MiniStat label={isZh ? "置信度" : "Confidence"} value={`${((regime?.confidence ?? 0) * 100).toFixed(0)}%`} color="#06b6d4" />
              <MiniStat label={isZh ? "动量(MA斜率)" : "Momentum(MA slope)"} value={`${regime?.ma_slope_pct?.toFixed(2)}%`}
                color={(regime?.ma_slope_pct ?? 0) >= 0 ? "#00c076" : "#f6465d"} />
              <MiniStat label={isZh ? "波动率(ATR)" : "Volatility(ATR)"} value={`${regime?.atr_pct?.toFixed(2)}%`}
                color={(regime?.volatility_percentile ?? 0) > 0.7 ? "#f6465d" : "#f0b90b"} />
            </div>
          </div>

          {/* 2. 权重自适应 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <SlidersHorizontal size={13} className="text-okx-yellow" />
              <span className="text-xs font-semibold text-dark-200">{isZh ? "2. 权重自适应" : "2. Weight Adaptation"}</span>
            </div>
            {weights.length === 0 ? (
              <p className="text-xs text-dark-500">{isZh ? "策略池为空" : "Strategy pool empty"}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-dark-400 border-b border-dark-800">
                      <th className="text-left py-1.5 pr-2">{isZh ? "策略" : "Strategy"}</th>
                      <th className="text-left px-2 py-1.5">{isZh ? "类型" : "Type"}</th>
                      <th className="text-right px-2 py-1.5">{isZh ? "池权重" : "Pool"}</th>
                      <th className="text-right px-2 py-1.5">{isZh ? "Regime乘数" : "×Regime"}</th>
                      <th className="text-right pl-2 py-1.5">{isZh ? "有效权重" : "Effective"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {weights.map((w: any, i: number) => (
                      <tr key={w.strategy_id || i} className="border-b border-dark-800/50 last:border-0">
                        <td className="py-1.5 pr-2 text-dark-200">{w.name}</td>
                        <td className="px-2 py-1.5 text-dark-400">{w.type}</td>
                        <td className="text-right px-2 py-1.5 font-mono">{w.pool_weight?.toFixed(3)}</td>
                        <td className="text-right px-2 py-1.5 font-mono">{w.regime_multiplier?.toFixed(2)}</td>
                        <td className={`text-right pl-2 py-1.5 font-mono ${w.compatible ? "text-dark-200" : "text-okx-red"}`}>
                          {w.effective_weight?.toFixed(4)}{!w.compatible ? (isZh ? " (不兼容)" : " (off)") : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* 3. 风控 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <ShieldCheck size={13} className="text-okx-green" />
              <span className="text-xs font-semibold text-dark-200">{isZh ? "3. 风控（当前 Regime）" : "3. Risk (current regime)"}</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              <MiniStat label={isZh ? "最大仓位" : "Max Position"} value={`${((policy?.max_position_pct ?? 0) * 100).toFixed(0)}%`} color="#eaecef" />
              <MiniStat label={isZh ? "单策略上限" : "Per-Strategy"} value={`${((policy?.max_single_strategy_pct ?? 0) * 100).toFixed(0)}%`} color="#eaecef" />
              <MiniStat label={isZh ? "硬止损" : "Stop Loss"} value={`${policy?.stop_loss_pct ?? 0}%`} color="#f6465d" />
              <MiniStat label={isZh ? "日亏上限" : "Daily Loss"} value={`${policy?.max_daily_loss_pct ?? 0}%`} color="#f6465d" />
              <MiniStat label={isZh ? "移动止损" : "Trailing"} value={`${policy?.trailing_stop_pct ?? 0}%`} color="#f0b90b" />
              <MiniStat label={isZh ? "最低入场夏普" : "Min Sharpe"} value={`${policy?.min_sharpe_entry ?? 0}`} color="#06b6d4" />
              <MiniStat label={isZh ? "最大相关性" : "Max Corr"} value={`${policy?.max_correlation ?? 0}`} color="#06b6d4" />
              <MiniStat label={isZh ? "ATR止损倍数" : "ATR Stop ×"} value={`${policy?.atr_stop_multiplier ?? 0}`} color="#a855f7" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-dark-900/50 border border-dark-800 rounded px-2 py-1.5">
      <div className="text-[10px] text-dark-500">{label}</div>
      <div className="font-mono font-semibold mt-0.5" style={{ color }}>{value}</div>
    </div>
  );
}
