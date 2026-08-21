import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import { RefreshCw, Layers, ListOrdered, History, Info } from "lucide-react";

/**
 * 交易页 — v6 问题5：取消手动交易，改为只读展示「策略启动后」的
 * 合约持仓 / 挂单 / 已平仓成交。
 */
export default function TradingPage() {
  const [positions, setPositions] = useState<any>(null);
  const [orders, setOrders] = useState<any[]>([]);
  const [trades, setTrades] = useState<any[]>([]);
  const [balance, setBalance] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const { lang } = useLanguage();
  const isZh = lang === "zh";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pos, ords, trs, bal] = await Promise.all([
        api.getPositions(),
        api.getOpenOrders(),
        api.getTradeHistory(20),
        api.getBalance(),
      ]);
      setPositions(pos);
      setOrders((ords ?? []) as any[]);
      setTrades((trs ?? []) as any[]);
      setBalance(bal as Record<string, any>);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const posList = positions?.positions ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">{isZh ? "交易情况" : "Trading"}</h2>
          <p className="text-xs text-dark-400 mt-1">
            {isZh ? "策略自动交易的持仓 / 挂单 / 成交（手动交易已取消）" : "Strategy-driven positions / orders / trades (manual trading removed)"}
          </p>
        </div>
        <button onClick={load} className="btn-ghost flex items-center gap-2 text-xs">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> {isZh ? "刷新" : "Refresh"}
        </button>
      </div>

      {/* 余额概览 */}
      {balance && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label={isZh ? "USDT 可用" : "USDT Free"} value={`$${(balance.USDT?.free ?? 0).toFixed(2)}`} />
          <StatCard label={isZh ? "USDT 总额" : "USDT Total"} value={`$${(balance.USDT?.total ?? 0).toFixed(2)}`} />
          <StatCard label={isZh ? "持仓名义价值" : "Position Notional"} value={`$${(positions?.total_notional_usdt ?? 0).toFixed(2)}`} />
          <StatCard label={isZh ? "未实现盈亏" : "Unrealized PnL"} value={`$${(positions?.total_unrealized_pnl ?? 0).toFixed(2)}`}
            color={(positions?.total_unrealized_pnl ?? 0) >= 0 ? "#00c076" : "#f6465d"} />
        </div>
      )}

      {/* 当前持仓 */}
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <Layers size={16} className="text-okx-blue" />
          <span className="text-sm font-semibold text-white">{isZh ? "当前持仓" : "Positions"}</span>
          <span className="text-xs text-dark-400 ml-auto">{posList.length} {isZh ? "个" : "pos"}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-dark-400 border-b border-dark-800">
                <th className="text-left py-2 pr-3">{isZh ? "交易对" : "Symbol"}</th>
                <th className="text-left px-2 py-2">{isZh ? "方向" : "Side"}</th>
                <th className="text-right px-2 py-2">{isZh ? "张数" : "Contracts"}</th>
                <th className="text-right px-2 py-2">{isZh ? "开仓价" : "Entry"}</th>
                <th className="text-right px-2 py-2">{isZh ? "标记价" : "Mark"}</th>
                <th className="text-right px-2 py-2">{isZh ? "名义价值" : "Notional"}</th>
                <th className="text-right px-2 py-2">{isZh ? "未实现盈亏" : "uPnL"}</th>
                <th className="text-right pl-2 py-2">{isZh ? "杠杆" : "Lev"}</th>
              </tr>
            </thead>
            <tbody>
              {posList.length === 0 && (
                <tr><td colSpan={8} className="text-center py-8 text-dark-500">{isZh ? "暂无持仓" : "No positions"}</td></tr>
              )}
              {posList.map((p: any, i: number) => (
                <tr key={i} className="border-b border-dark-800/50">
                  <td className="py-2.5 pr-3 font-medium text-dark-200">{p.symbol}</td>
                  <td className={`px-2 py-2 font-medium ${p.side === "long" ? "text-green" : "text-red"}`}>
                    {p.side === "long" ? (isZh ? "多" : "LONG") : (isZh ? "空" : "SHORT")}
                  </td>
                  <td className="text-right px-2 py-2 font-mono">{p.contracts}</td>
                  <td className="text-right px-2 py-2 font-mono">${p.entry_price?.toFixed(4)}</td>
                  <td className="text-right px-2 py-2 font-mono">${p.mark_price?.toFixed(4)}</td>
                  <td className="text-right px-2 py-2 font-mono">${p.notional_usdt?.toFixed(2)}</td>
                  <td className={`text-right px-2 py-2 font-mono ${(p.unrealized_pnl || 0) >= 0 ? "text-green" : "text-red"}`}>
                    {(p.unrealized_pnl || 0) >= 0 ? "+" : ""}{p.unrealized_pnl?.toFixed(2)} ({p.pnl_pct?.toFixed(2)}%)
                  </td>
                  <td className="text-right pl-2 py-2 font-mono">{p.leverage}x</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 挂单 */}
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <ListOrdered size={16} className="text-okx-yellow" />
          <span className="text-sm font-semibold text-white">{isZh ? "挂单" : "Open Orders"}</span>
          <span className="text-xs text-dark-400 ml-auto">{orders.length} {isZh ? "笔" : "orders"}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-dark-400 border-b border-dark-800">
                <th className="text-left py-2 pr-3">{isZh ? "交易对" : "Symbol"}</th>
                <th className="text-left px-2 py-2">{isZh ? "方向" : "Side"}</th>
                <th className="text-right px-2 py-2">{isZh ? "价格" : "Price"}</th>
                <th className="text-right px-2 py-2">{isZh ? "数量" : "Amount"}</th>
                <th className="text-right px-2 py-2">{isZh ? "已成交" : "Filled"}</th>
                <th className="text-right pl-2 py-2">{isZh ? "状态" : "Status"}</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 && (
                <tr><td colSpan={6} className="text-center py-8 text-dark-500">{isZh ? "暂无挂单" : "No open orders"}</td></tr>
              )}
              {orders.map((o: any, i: number) => (
                <tr key={o.id || i} className="border-b border-dark-800/50">
                  <td className="py-2.5 pr-3 font-medium text-dark-200">{o.symbol}</td>
                  <td className={`px-2 py-2 font-medium ${o.side === "buy" ? "text-green" : "text-red"}`}>{o.side?.toUpperCase()}</td>
                  <td className="text-right px-2 py-2 font-mono">${Number(o.price ?? 0).toFixed(2)}</td>
                  <td className="text-right px-2 py-2 font-mono">{Number(o.amount ?? 0).toFixed(6)}</td>
                  <td className="text-right px-2 py-2 font-mono">{Number(o.filled ?? 0).toFixed(6)}</td>
                  <td className="text-right pl-2 py-2 text-dark-400">{o.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 已平仓成交 */}
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <History size={16} className="text-okx-green" />
          <span className="text-sm font-semibold text-white">{isZh ? "已平仓成交" : "Closed Trades"}</span>
          <span className="text-xs text-dark-400 ml-auto">{trades.length} {isZh ? "笔" : "trades"}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-dark-400 border-b border-dark-800">
                <th className="text-left py-2 pr-3">{isZh ? "交易对" : "Symbol"}</th>
                <th className="text-right px-2 py-2">{isZh ? "买入价" : "Buy"}</th>
                <th className="text-right px-2 py-2">{isZh ? "卖出价" : "Sell"}</th>
                <th className="text-right px-2 py-2">{isZh ? "数量" : "Qty"}</th>
                <th className="text-right px-2 py-2">{isZh ? "盈亏" : "PnL"}</th>
                <th className="text-right px-2 py-2">{isZh ? "盈亏%" : "PnL%"}</th>
                <th className="text-right pl-2 py-2">{isZh ? "时间" : "Time"}</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 && (
                <tr><td colSpan={7} className="text-center py-8 text-dark-500">{isZh ? "暂无成交" : "No closed trades"}</td></tr>
              )}
              {trades.map((t: any, i: number) => (
                <tr key={t.id || i} className="border-b border-dark-800/50">
                  <td className="py-2.5 pr-3 font-medium text-dark-200">{t.symbol}</td>
                  <td className="text-right px-2 py-2 font-mono">${Number(t.buy_price ?? 0).toFixed(2)}</td>
                  <td className="text-right px-2 py-2 font-mono">${Number(t.sell_price ?? 0).toFixed(2)}</td>
                  <td className="text-right px-2 py-2 font-mono">{Number(t.quantity ?? 0).toFixed(6)}</td>
                  <td className={`text-right px-2 py-2 font-mono ${(t.profit || 0) >= 0 ? "text-green" : "text-red"}`}>
                    {(t.profit || 0) >= 0 ? "+" : ""}{Number(t.profit ?? 0).toFixed(4)}
                  </td>
                  <td className={`text-right px-2 py-2 font-mono ${(t.profit_pct || 0) >= 0 ? "text-green" : "text-red"}`}>
                    {(t.profit_pct || 0) >= 0 ? "+" : ""}{Number(t.profit_pct ?? 0).toFixed(2)}%
                  </td>
                  <td className="text-right pl-2 py-2 text-dark-400">
                    {t.closed_at ? new Date(t.closed_at).toLocaleTimeString() : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card border-dark-700 flex items-start gap-2">
        <Info size={14} className="text-dark-500 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-dark-400 leading-relaxed">
          {isZh
            ? "手动下单已取消。所有交易由「策略」自动执行：启动策略后，此处展示策略产生的合约持仓、挂单与已平仓成交。平仓通过策略的止损/信号自动完成。"
            : "Manual trading removed. All trades are executed automatically by strategies; this page shows their positions, open orders and closed trades."}
        </p>
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="card py-3">
      <div className="text-xs text-dark-400 mb-1">{label}</div>
      <div className="text-sm font-bold font-mono" style={{ color: color || "#eaecef" }}>{value}</div>
    </div>
  );
}
