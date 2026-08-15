import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import {
  Briefcase, RefreshCw, TrendingUp, TrendingDown,
  ArrowUp, ArrowDown, Minus, X,
} from "lucide-react";

// v2.0 合约版：持仓字段与后端 /api/portfolio/positions 对齐（fetch_positions 口径）
interface PositionItem {
  symbol: string;
  side: "long" | "short";
  contracts: number;
  entry_price: number;
  mark_price: number;
  notional_usdt: number;
  unrealized_pnl: number;
  pnl_pct: number;
  leverage: number;
}

interface PositionsData {
  positions: PositionItem[];
  total_notional_usdt: number;
  total_unrealized_pnl: number;
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
  const { lang } = useLanguage();
  const [data, setData] = useState<PositionsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshInterval] = useState(3000); // 3s 实时刷新
  const [flashPnl, setFlashPnl] = useState<"up" | "down" | null>(null);
  const prevPnlRef = useRef<number | null>(null);
  const [closing, setClosing] = useState<string | null>(null);  // 正在平仓的交易对

  const handleClose = async (symbol: string, side: string, contracts: number) => {
    const asset = symbol.split("/")[0];
    const ok = window.confirm(
      isZh
        ? `确认市价平仓 ${symbol}（${side === "long" ? "多" : "空"}）？\n\n张数：${contracts} 张\n将以 reduce-only 市价单平仓。`
        : `Confirm market close ${symbol} (${side})?\n\nContracts: ${contracts}\nWill close with a reduce-only market order.`
    );
    if (!ok) return;
    setClosing(symbol);
    try {
      await api.closePosition(asset, true);
      load(); // 刷新数据
    } catch (e) {
      console.error("Close position failed:", e);
    }
    setClosing(null);
  };

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
  const notional = p?.total_notional_usdt ?? 0;
  // 开仓成本名义 = 当前名义 - 未实现盈亏
  const costBasis = notional - pnl;
  const pnlPct = costBasis > 0 ? (pnl / costBasis) * 100 : 0;

  return (
    <div className="space-y-4">
      {/* ===== 核心：大号实时盈亏 ===== */}
      <div
        className="card p-6 text-center transition-colors duration-300"
        style={{ background: pnlBg(pnl) }}
      >
        <p className="text-xs text-dark-400 mb-1">
          {isZh ? "合约浮动盈亏 · 实时" : "Unrealized PnL · Realtime"}
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

        {/* 名义价值概览条 */}
        <div className="mt-4 max-w-md mx-auto flex justify-between text-xs text-dark-400">
          <span>{isZh ? "开仓名义" : "Entry Notional"}: ${costBasis.toLocaleString()}</span>
          <span>{isZh ? "当前名义" : "Mark Notional"}: ${notional.toLocaleString()}</span>
        </div>
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
          <span className="text-dark-600 text-[10px] ml-2 px-1.5 py-0.5 border border-dark-700 rounded">v2.0.0 合约版</span>
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
                <th className="text-left py-2.5 px-3 font-medium">{isZh ? "合约" : "Symbol"}</th>
                <th className="text-left py-2.5 px-3 font-medium">{isZh ? "方向" : "Side"}</th>
                <th className="text-right py-2.5 px-3 font-medium">{isZh ? "张数" : "Contracts"}</th>
                <th className="text-right py-2.5 px-3 font-medium hidden sm:table-cell">{isZh ? "开仓价" : "Entry"}</th>
                <th className="text-right py-2.5 px-3 font-medium">{isZh ? "标记价" : "Mark"}</th>
                <th className="text-right py-2.5 px-3 font-medium hidden md:table-cell">{isZh ? "名义" : "Notional"}</th>
                <th className="text-right py-2.5 px-3 font-medium">{isZh ? "盈亏" : "PnL"}</th>
                <th className="text-center py-2.5 px-3 font-medium">{isZh ? "操作" : "Action"}</th>
              </tr>
            </thead>
            <tbody>
              {p.positions.map((pos) => {
                const pnl = pos.unrealized_pnl ?? 0;
                const pnlP = pos.pnl_pct ?? 0;
                const asset = pos.symbol.split("/")[0];
                return (
                  <tr
                    key={pos.symbol + pos.side}
                    className="border-b border-dark-800 hover:bg-dark-850 transition-colors"
                    style={{ background: pnlBg(pnl) }}
                  >
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
                          style={{
                            background: `hsl(${(asset.charCodeAt(0) || 0) * 137 % 360}, 60%, 30%)`,
                            color: "#fff",
                          }}
                        >
                          {asset[0]}
                        </div>
                        <span className="text-white font-medium">{asset}</span>
                        <span className="text-dark-500 text-[10px]">{pos.leverage}x</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          pos.side === "long"
                            ? "bg-green-500/20 text-green-400"
                            : "bg-red-500/20 text-red-400"
                        }`}
                      >
                        {pos.side === "long" ? (isZh ? "多" : "LONG") : (isZh ? "空" : "SHORT")}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-white text-xs">
                      {pos.contracts.toLocaleString("en-US", { maximumFractionDigits: 6 })}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-dark-300 text-xs hidden sm:table-cell">
                      ${pos.entry_price.toFixed(6)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-white text-xs">
                      ${pos.mark_price.toFixed(6)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-white text-xs hidden md:table-cell">
                      ${pos.notional_usdt.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <div className="flex flex-col items-end">
                        <span className="font-mono font-bold text-xs" style={{ color: pnlColor(pnl) }}>
                          {fmt$(pnl)}
                        </span>
                        <span className="text-[10px]" style={{ color: pnlColor(pnl) }}>
                          {pnlSign(pnlP)}{Math.abs(pnlP).toFixed(2)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <button
                        onClick={() => handleClose(pos.symbol, pos.side, pos.contracts)}
                        disabled={closing === pos.symbol}
                        className="px-3 py-1.5 rounded text-xs font-bold transition-all duration-200
                          bg-red-500/20 text-red-400 hover:bg-red-500 hover:text-white
                          border border-red-500/40 hover:border-red-500
                          disabled:opacity-50 disabled:cursor-not-allowed
                          shadow-sm hover:shadow-md active:scale-95"
                        title={isZh ? "reduce-only 市价平仓" : "Reduce-only close at market"}
                      >
                        {closing === pos.symbol ? (
                          <RefreshCw size={13} className="animate-spin inline" />
                        ) : (
                          <X size={13} className="inline" />
                        )}
                        <span className="ml-1 hidden sm:inline">
                          {isZh ? "平仓" : "Close"}
                        </span>
                      </button>
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
                <td className="py-2.5 px-3" />
                <td className="py-2.5 px-3" />
                <td className="py-2.5 px-3 hidden sm:table-cell" />
                <td className="py-2.5 px-3 hidden md:table-cell" />
                <td className="py-2.5 px-3 text-right font-mono text-white text-xs hidden md:table-cell">
                  ${notional.toFixed(2)}
                </td>
                <td className="py-2.5 px-3 text-right font-mono font-bold text-xs" style={{ color: pnlColor(pnl) }}>
                  {fmt$(pnl)} ({pnlSign(pnlPct)}{Math.abs(pnlPct).toFixed(2)}%)
                </td>
                <td className="py-2.5 px-3" />
              </tr>
            </tfoot>
          </table>
        )}
      </div>
    </div>
  );
}
