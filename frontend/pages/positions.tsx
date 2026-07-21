import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import {
  Briefcase, RefreshCw, TrendingUp, TrendingDown,
  ArrowUp, ArrowDown, Minus,
} from "lucide-react";

interface PositionItem {
  symbol: string;
  asset: string;
  quantity: number;
  current_price: number;
  value_usdt: number;
  avg_buy_price: number | null;
  total_buy_cost: number | null;
  unrealized_pnl: number | null;
  pnl_pct: number | null;
  change_24h_pct: number;
  realized_pnl: number;
}

interface PositionsData {
  positions: PositionItem[];
  total_value_usdt: number;
  total_buy_cost: number;
  total_unrealized_pnl: number;
  total_pnl_pct: number;
  count: number;
}

// 涨跌颜色（绿涨红跌）
function pnlColor(val: number | null | undefined): string {
  if (val === null || val === undefined) return "#9ca3af";
  if (val > 0) return "#34d399";
  if (val < 0) return "#f87171";
  return "#9ca3af";
}

function pnlBg(val: number | null | undefined): string {
  if (val === null || val === undefined) return "rgba(255,255,255,0.03)";
  if (val > 0) return "rgba(52,211,153,0.10)";
  if (val < 0) return "rgba(248,113,113,0.10)";
  return "rgba(255,255,255,0.03)";
}

function pnlSign(val: number | null | undefined): string {
  if (val === null || val === undefined) return "";
  if (val > 0) return "+";
  return "";
}

/** 格式化金额（千分位 + 固定小数） */
function fmt$(val: number | null | undefined, decimals = 2): string {
  if (val === null || val === undefined) return "—";
  return (pnlSign(val) + Math.abs(val).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }));
}

/** 盈亏动画指示器 */
function PnlArrow({ pnl }: { pnl: number | null | undefined }) {
  if (pnl === null || pnl === undefined || pnl === 0) {
    return <Minus size={16} className="text-dark-500" />;
  }
  if (pnl > 0) return <ArrowUp size={16} className="text-green-400" />;
  return <ArrowDown size={16} className="text-red-400" />;
}

export default function PositionsPage() {
  const { t, lang } = useLanguage();
  const [data, setData] = useState<PositionsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshInterval] = useState(3000); // 3s 实时刷新
  const [flashPnl, setFlashPnl] = useState<"up" | "down" | null>(null);
  const prevPnlRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const res = (await api.getPositions()) as any;
      const posData: PositionsData = res?.data ?? res;

      // 盈亏变化方向检测（用于闪烁动画）
      const newPnl = posData?.total_unrealized_pnl ?? 0;
      if (prevPnlRef.current !== null) {
        if (newPnl > prevPnlRef.current) setFlashPnl("up");
        else if (newPnl < prevPnlRef.current) setFlashPnl("down");
        if (newPnl !== prevPnlRef.current) {
          setTimeout(() => setFlashPnl(null), 600);
        }
      }
      prevPnlRef.current = newPnl;
      setData(posData);
    } catch (e) {
      console.error("Positions fetch error:", e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // 自动刷新
  useEffect(() => {
    const timer = setInterval(load, refreshInterval);
    return () => clearInterval(timer);
  }, [load, refreshInterval]);

  const isZh = lang === "zh";
  const p = data;
  const pnl = p?.total_unrealized_pnl ?? 0;
  const pnlPct = p?.total_pnl_pct ?? 0;
  const buyCost = p?.total_buy_cost ?? 0;
  const curValue = p?.total_value_usdt ?? 0;

  return (
    <div className="space-y-4">
      {/* ===== 核心：大号实时盈亏 ===== */}
      <div
        className="card p-6 text-center transition-colors duration-300"
        style={{ background: pnlBg(pnl) }}
      >
        <p className="text-xs text-dark-400 mb-1">
          {isZh ? "浮动盈亏 · 实时" : "Unrealized PnL · Realtime"}
        </p>
        <div className="flex items-center justify-center gap-3">
          <PnlArrow pnl={pnl} />
          <span
            className="text-4xl font-bold font-mono transition-colors duration-300"
            style={{ color: pnlColor(pnl) }}
          >
            <span className={`inline-block transition-all duration-300 ${
              flashPnl === "up" ? "scale-110 text-green-400" : flashPnl === "down" ? "scale-95 text-red-400" : ""
            }`}>
              {fmt$(pnl)}
            </span>
          </span>
          <span className="text-xl font-mono" style={{ color: pnlColor(pnl) }}>
            ({pnlSign(pnl)}{Math.abs(pnlPct).toFixed(2)}%)
          </span>
        </div>

        {/* 成本 vs 市值对比条 */}
        {buyCost > 0 && (
          <div className="mt-4 max-w-md mx-auto">
            <div className="flex justify-between text-xs text-dark-400 mb-1">
              <span>{isZh ? "投入成本" : "Cost"}: ${buyCost.toLocaleString()}</span>
              <span>{isZh ? "当前市值" : "Value"}: ${curValue.toLocaleString()}</span>
            </div>
            <div className="h-2 bg-dark-700 rounded-full overflow-hidden flex">
              <div
                className="h-full transition-all duration-500"
                style={{
                  width: `${Math.min(buyCost / Math.max(curValue, 1) * 100, 100)}%`,
                  background: curValue >= buyCost
                    ? "linear-gradient(90deg, #34d399, #fbbf24)"
                    : "linear-gradient(90deg, #f87171, #34d399)",
                }}
              />
              {curValue > 0 && (
                <div
                  className="h-full transition-all duration-500"
                  style={{
                    width: `${Math.abs(pnl) / Math.max(curValue, 1) * 100}%`,
                    backgroundColor: pnl >= 0 ? "rgba(52,211,153,0.3)" : "rgba(248,113,113,0.3)",
                  }}
                />
              )}
            </div>
          </div>
        )}
      </div>

      {/* ===== 刷新状态 ===== */}
      <div className="flex items-center justify-between text-xs text-dark-500">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${loading ? "bg-yellow-400 animate-pulse" : "bg-okx-green"}`} />
          {isZh ? `每 ${refreshInterval / 1000}s 自动刷新` : `Auto refresh ${refreshInterval / 1000}s`}
          <span>·</span>
          <span>
            {isZh ? `${p?.count ?? 0} 个持仓` : `${p?.count ?? 0} positions`}
          </span>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="btn-secondary flex items-center gap-1 text-xs py-1 px-2"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          {isZh ? "刷新" : "Refresh"}
        </button>
      </div>

      {/* ===== 持仓表格 ===== */}
      <div className="card overflow-x-auto">
        {(!p || p.positions.length === 0) ? (
          <div className="text-center py-12 text-dark-400 text-sm">
            <Briefcase size={32} className="mx-auto mb-3 text-dark-600" />
            {isZh ? "暂无持仓" : "No positions"}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-dark-800 text-dark-400 text-xs">
                <th className="text-left py-2.5 px-3 font-medium">{isZh ? "币种" : "Asset"}</th>
                <th className="text-right py-2.5 px-3 font-medium">{isZh ? "数量" : "Qty"}</th>
                <th className="text-right py-2.5 px-3 font-medium hidden sm:table-cell">{isZh ? "买入均价" : "Avg Buy"}</th>
                <th className="text-right py-2.5 px-3 font-medium">{isZh ? "现价" : "Now"}</th>
                <th className="text-right py-2.5 px-3 font-medium hidden md:table-cell">{isZh ? "投入" : "Cost"}</th>
                <th className="text-right py-2.5 px-3 font-medium hidden md:table-cell">{isZh ? "市值" : "Value"}</th>
                <th className="text-right py-2.5 px-3 font-medium">{isZh ? "盈亏" : "PnL"}</th>
              </tr>
            </thead>
            <tbody>
              {p.positions.map((pos) => {
                const hasPnl = pos.unrealized_pnl !== null;
                const pnl = pos.unrealized_pnl ?? 0;
                const pnlP = pos.pnl_pct ?? 0;
                return (
                  <tr
                    key={pos.symbol}
                    className="border-b border-dark-800 hover:bg-dark-850 transition-colors"
                    style={{ background: hasPnl ? pnlBg(pnl) : undefined }}
                  >
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
                          style={{
                            background: `hsl(${(pos.asset.charCodeAt(0) || 0) * 137 % 360}, 60%, 30%)`,
                            color: "#fff",
                          }}
                        >
                          {pos.asset[0]}
                        </div>
                        <span className="text-white font-medium">{pos.asset}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-white text-xs">
                      {pos.quantity.toFixed(pos.quantity >= 1 ? 4 : 6)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-dark-300 text-xs hidden sm:table-cell">
                      {pos.avg_buy_price !== null ? `$${pos.avg_buy_price.toFixed(2)}` : "—"}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-white text-xs">
                      ${pos.current_price.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-dark-300 text-xs hidden md:table-cell">
                      {pos.total_buy_cost !== null ? `$${pos.total_buy_cost.toFixed(2)}` : "—"}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-white text-xs hidden md:table-cell">
                      ${pos.value_usdt.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      {hasPnl ? (
                        <div className="flex flex-col items-end">
                          <span className="font-mono font-bold text-xs" style={{ color: pnlColor(pnl) }}>
                            {fmt$(pnl)}
                          </span>
                          <span className="text-[10px]" style={{ color: pnlColor(pnl) }}>
                            {pnlSign(pnlP)}{Math.abs(pnlP).toFixed(2)}%
                          </span>
                        </div>
                      ) : (
                        <span className="text-dark-500 text-xs">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-dark-700 bg-dark-850/50">
                <td className="py-2.5 px-3 text-xs text-dark-400 font-medium">
                  {isZh ? "合计" : "Total"}
                </td>
                <td className="py-2.5 px-3 text-right text-xs text-dark-400" />
                <td className="py-2.5 px-3 hidden sm:table-cell" />
                <td className="py-2.5 px-3 hidden md:table-cell" />
                <td className="py-2.5 px-3 text-right font-mono text-dark-300 text-xs hidden md:table-cell">
                  ${buyCost.toFixed(2)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono text-white text-xs hidden md:table-cell">
                  ${curValue.toFixed(2)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono font-bold text-xs" style={{ color: pnlColor(pnl) }}>
                  {fmt$(pnl)} ({pnlSign(pnlPct)}{Math.abs(pnlPct).toFixed(2)}%)
                </td>
              </tr>
            </tfoot>
          </table>
        )}
      </div>
    </div>
  );
}
