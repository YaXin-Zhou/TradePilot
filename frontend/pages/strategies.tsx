import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import { Plus, Play, Square, BarChart3, Trash2, Layers, Zap, Moon, TrendingUp, ScrollText, ChevronDown, ChevronUp, Shield } from "lucide-react";

const LOG_COLORS: Record<string, string> = {
  created: "#fbbf24",
  started: "#34d399",
  stopped: "#f87171",
  deleted: "#ef4444",
  signal_buy: "#34d399",
  signal_sell: "#f87171",
  order_placed: "#38bdf8",
  order_error: "#ef4444",
  stop_loss: "#f97316",
  heartbeat: "#6b7280",
  error: "#ef4444",
};

const LOG_LABELS: Record<string, string> = {
  created: "创建",
  started: "启动",
  stopped: "停止",
  deleted: "删除",
  signal_buy: "买入信号",
  signal_sell: "卖出信号",
  order_placed: "下单",
  order_error: "下单失败",
  stop_loss: "止损",
  heartbeat: "心跳",
  error: "错误",
};

interface LogEntry {
  strategy_id: string;
  event_type: string;
  message: string;
  created_at: string;
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<any[]>([]);
  const [poolSummary, setPoolSummary] = useState<any>(null);
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState("Grid Strategy");
  const [type, setType] = useState("grid");
  const [lower, setLower] = useState("83000");
  const [upper, setUpper] = useState("93000");
  const [grids, setGrids] = useState("20");
  const [amount, setAmount] = useState("100");
  // 策略风控参数
  const [stopLossPct, setStopLossPct] = useState("5");
  const [trailingStopPct, setTrailingStopPct] = useState("2");
  const [maxPositionPct, setMaxPositionPct] = useState("10");
  const [riskPerTradePct, setRiskPerTradePct] = useState("1");
  const [showRiskConfig, setShowRiskConfig] = useState(false);
  const [logState, setLogState] = useState<Record<string, { open: boolean; logs: LogEntry[]; loading: boolean }>>({});
  const { t, lang } = useLanguage();
  const isZh = lang === "zh";

  const load = useCallback(async () => {
    try {
      const [strats, pool] = await Promise.all([
        api.listStrategies(),
        api.getPoolSummary(),
      ]);
      // 运行中的策略置顶
      const sorted = ((strats ?? []) as Record<string, unknown>[]).sort((a, b) => {
        if ((a.status as string) === "running" && (b.status as string) !== "running") return -1;
        if ((a.status as string) !== "running" && (b.status as string) === "running") return 1;
        return 0;
      });
      setStrategies(sorted);
      if (pool?.success) setPoolSummary(pool.data);
    } catch {}
  }, []);

  useEffect(() => { load(); }, [load]);

  const createStrategy = async () => {
    await api.createStrategy({ name, type, symbol: "BTC/USDT", config: {
      lower_bound: parseFloat(lower), upper_bound: parseFloat(upper), grid_count: parseInt(grids), order_amount: parseFloat(amount),
      stop_loss_pct: parseFloat(stopLossPct) || 0,
      trailing_stop_pct: parseFloat(trailingStopPct) || 0,
      max_position_pct: parseFloat(maxPositionPct) || 0,
      risk_per_trade_pct: parseFloat(riskPerTradePct) || 0,
    }});
    setShowNew(false);
    load();
  };

  const toggleStrategy = async (s: Record<string, any>) => {
    await api.updateStrategy(s.id, { status: s.status === "running" ? "stopped" : "running" });
    load();
  };

  const deleteStrategy = async (id: string) => { await api.stopStrategy(id).catch(()=>{}); await api.deleteStrategy(id); load(); };

  const toggleLog = async (id: string) => {
    const current = logState[id];
    if (current?.open) {
      setLogState((prev) => ({ ...prev, [id]: { ...prev[id], open: false } }));
      return;
    }
    // 展开时加载日志
    setLogState((prev) => ({ ...prev, [id]: { open: true, logs: [], loading: true } }));
    try {
      const res = await api.getStrategyLogs(id, 100);
      // request() 已经解包 json.data，res 本身就是日志数组
      const logs: LogEntry[] = Array.isArray(res) ? (res as LogEntry[]) : ((res as { data?: unknown })?.data as LogEntry[] ?? []);
      setLogState((prev) => ({
        ...prev,
        [id]: { open: true, logs, loading: false },
      }));
    } catch {
      setLogState((prev) => ({ ...prev, [id]: { ...prev[id], loading: false } }));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">{t("strat.title")}</h2>
          <p className="text-xs text-dark-400 mt-1">{t("strat.subtitle")}</p>
        </div>
        <button onClick={() => setShowNew(!showNew)} className="btn-primary flex items-center gap-2 text-sm">
          <Plus size={16} /> {t("strat.new")}
        </button>
      </div>

      {/* Pool Summary Cards */}
      {poolSummary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label={t("pool.totalStrategies")} value={poolSummary.total_strategies} icon={Layers} color="#f0b90b" />
          <StatCard label={t("pool.activeCount")} value={poolSummary.active_count} icon={Zap} color="#00c076" />
          <StatCard label={t("pool.sleepingCount")} value={poolSummary.sleeping_count} icon={Moon} color="#f59e0b" />
          <StatCard label={t("pool.avgSharpe")} value={poolSummary.avg_sharpe?.toFixed(2)} icon={TrendingUp} color="#06b6d4" />
        </div>
      )}

      {showNew && (
        <div className="card border-okx-green/30">
          <h3 className="text-sm font-semibold text-white mb-4">{t("strat.new")}</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div><label className="text-xs text-dark-400 block mb-1">{t("strat.name")}</label><input value={name} onChange={(e) => setName(e.target.value)} className="w-full" /></div>
            <div><label className="text-xs text-dark-400 block mb-1">{t("strat.type")}</label>
              <select value={type} onChange={(e) => setType(e.target.value)} className="w-full">
                <option value="grid">{t("strat.gridTrading")}</option>
                <option value="ml_signal">{t("strat.mlSignal")}</option>
                <option value="sma_cross">{t("strat.smaCross")}</option>
              </select>
            </div>
            <div><label className="text-xs text-dark-400 block mb-1">{t("strat.lower")}</label><input type="number" value={lower} onChange={(e) => setLower(e.target.value)} className="w-full" /></div>
            <div><label className="text-xs text-dark-400 block mb-1">{t("strat.upper")}</label><input type="number" value={upper} onChange={(e) => setUpper(e.target.value)} className="w-full" /></div>
            <div><label className="text-xs text-dark-400 block mb-1">{t("strat.gridCount")}</label><input type="number" value={grids} onChange={(e) => setGrids(e.target.value)} className="w-full" /></div>
            <div><label className="text-xs text-dark-400 block mb-1">{t("strat.orderAmt")}</label><input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} className="w-full" /></div>
          </div>

          {/* 策略风控参数 — 可折叠 */}
          <button
            onClick={() => setShowRiskConfig(!showRiskConfig)}
            className="flex items-center gap-2 text-xs text-dark-400 hover:text-dark-200 mb-3 transition-colors"
          >
            <Shield size={13} />
            {isZh ? "风控参数（可选）" : "Risk Params (optional)"}
            {showRiskConfig ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
          {showRiskConfig && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4 p-3 rounded-lg bg-dark-800/30 border border-dark-700/50">
              <div>
                <label className="text-xs text-dark-500 block mb-1">
                  {isZh ? "止损 %" : "Stop Loss %"}
                  <span className="text-dark-600 ml-0.5">(0={isZh?"关":"off"})</span>
                </label>
                <input type="number" value={stopLossPct} onChange={(e) => setStopLossPct(e.target.value)}
                  className="w-full text-xs py-1.5" min={0} step={0.5} placeholder="5" />
              </div>
              <div>
                <label className="text-xs text-dark-500 block mb-1">
                  {isZh ? "移动止损 %" : "Trailing Stop %"}
                </label>
                <input type="number" value={trailingStopPct} onChange={(e) => setTrailingStopPct(e.target.value)}
                  className="w-full text-xs py-1.5" min={0} step={0.5} placeholder="2" />
              </div>
              <div>
                <label className="text-xs text-dark-500 block mb-1">
                  {isZh ? "最大仓位 %" : "Max Position %"}
                </label>
                <input type="number" value={maxPositionPct} onChange={(e) => setMaxPositionPct(e.target.value)}
                  className="w-full text-xs py-1.5" min={0} max={100} step={1} placeholder="10" />
              </div>
              <div>
                <label className="text-xs text-dark-500 block mb-1">
                  {isZh ? "单笔风险 %" : "Risk/Trade %"}
                </label>
                <input type="number" value={riskPerTradePct} onChange={(e) => setRiskPerTradePct(e.target.value)}
                  className="w-full text-xs py-1.5" min={0} max={100} step={0.5} placeholder="1" />
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <button onClick={createStrategy} className="btn-primary text-sm">{t("strat.create")}</button>
            <button onClick={() => setShowNew(false)} className="btn-ghost text-sm">{t("strat.cancel")}</button>
          </div>
        </div>
      )}

      {strategies.length === 0 && (
        <div className="card text-center py-12">
          <BarChart3 size={40} className="mx-auto mb-3 text-dark-600" />
          <p className="text-dark-400 text-sm">{t("strat.none")}</p>
          <p className="text-dark-500 text-xs mt-1">{t("strat.noneHint")}</p>
        </div>
      )}

      <div className="grid gap-4">
        {strategies.map((s) => {
          const ls = logState[s.id] ?? { open: false, logs: [], loading: false };
          return (
          <div key={s.id}>
            <div className="card hover:border-dark-700 transition-colors">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className={`w-2 h-2 rounded-full ${s.status === "running" ? "bg-okx-green" : s.status === "paused" ? "bg-okx-yellow" : "bg-dark-500"}`} />
                <div>
                  <span className="text-sm font-semibold text-white">{s.name}</span>
                  <span className="ml-2 text-xs px-2 py-0.5 rounded bg-dark-800 text-dark-400">{s.type}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => toggleLog(s.id)} className="btn-ghost text-xs py-1.5 px-2 text-dark-400 hover:text-white flex items-center gap-1">
                  <ScrollText size={12} />
                  {isZh ? "日志" : "Log"}
                  {ls.open ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                </button>
                <button onClick={() => toggleStrategy(s)} className={`btn-ghost text-xs py-1.5 px-3 flex items-center gap-1 ${s.status === "running" ? "text-okx-red" : "text-okx-green"}`}>
                  {s.status === "running" ? <Square size={12} /> : <Play size={12} />}
                  {s.status === "running" ? t("strat.stop") : t("strat.start")}
                </button>
                <button onClick={() => deleteStrategy(s.id)} className="btn-ghost text-xs py-1.5 px-3 text-dark-400 hover:text-red"><Trash2 size={12} /></button>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-4 text-xs">
              <div><span className="text-dark-400">{t("strat.symbol")}</span><p className="font-mono text-dark-200 mt-0.5">{s.symbol}</p></div>
              <div><span className="text-dark-400">{t("strat.totalPnl")}</span><p className={`font-mono mt-0.5 ${(s.total_pnl || 0) >= 0 ? "text-green" : "text-red"}`}>{s.total_pnl?.toFixed(4)} USDT</p></div>
              <div><span className="text-dark-400">{t("strat.trades")}</span><p className="font-mono text-dark-200 mt-0.5">{s.total_trades || 0}</p></div>
              <div><span className="text-dark-400">{t("strat.winRate")}</span><p className="font-mono text-dark-200 mt-0.5">{s.win_rate ? `${(s.win_rate * 100).toFixed(1)}%` : "-"}</p></div>
            </div>
            </div>

            {/* 日志面板 */}
            {ls.open && (
              <div className="mt-1 card border-dark-700 bg-dark-900/50 p-3 max-h-64 overflow-y-auto">
                {ls.loading ? (
                  <p className="text-xs text-dark-400 text-center py-4">加载中...</p>
                ) : ls.logs.length === 0 ? (
                  <p className="text-xs text-dark-500 text-center py-4">{isZh ? "暂无日志" : "No logs yet"}</p>
                ) : (
                  <div className="space-y-1">
                    {ls.logs.map((entry, i) => {
                      const color = LOG_COLORS[entry.event_type] || "#6b7280";
                      const label = isZh ? (LOG_LABELS[entry.event_type] || entry.event_type) : entry.event_type;
                      const time = entry.created_at ? new Date(entry.created_at).toLocaleTimeString() : "";
                      return (
                        <div key={i} className="flex items-start gap-2 text-xs py-1 border-b border-dark-800/50 last:border-0">
                          <span className="text-dark-500 font-mono w-16 flex-shrink-0">{time}</span>
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium flex-shrink-0" style={{ background: color + "20", color }}>{label}</span>
                          <span className="text-dark-300 truncate">{entry.message}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        )})}
      </div>
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color }: { label: string; value: string | number | undefined; icon: React.ComponentType<Record<string, any>>; color: string }) {
  return (
    <div className="card flex items-center gap-3">
      <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: color + "20" }}>
        <Icon size={16} style={{ color }} />
      </div>
      <div>
        <p className="text-dark-400 text-xs">{label}</p>
        <p className="text-lg font-bold text-white">{value ?? "-"}</p>
      </div>
    </div>
  );
}