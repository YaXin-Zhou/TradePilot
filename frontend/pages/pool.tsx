import { useState, useEffect, useCallback } from "react";
import { useLanguage } from "../lib/LanguageContext";
import { api } from "../lib/api";
import { Layers, TrendingUp, Moon, Zap, RefreshCw } from "lucide-react";

const STATUS_COLORS: Record<string, string> = {
  active: "#00d4aa", deployed: "#06b6d4", sleeping: "#f59e0b",
  paused: "#6b7280", eliminated: "#ef4444",
};

export default function StrategyPoolPage() {
  const { t } = useLanguage();
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [correlation, setCorrelation] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([api.getPoolSummary(), api.getPoolCorrelation()]);
      if (s.success) setSummary(s.data);
      if (c.success) setCorrelation(c.data);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  async function toggleStatus(id: string, current: string) {
    const next = current === "active" ? "paused" : "active";
    await api.setPoolStatus(id, next);
    fetchData();
  }

  if (loading && !summary) {
    return <div className="page-container"><div className="skeleton h-96 rounded-xl" /></div>;
  }

  return (
    <div className="page-container">
      <div className="mb-6">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <Layers size={22} /> {t("pool.title")}
        </h1>
        <p className="text-dark-400 text-sm mt-1">{t("pool.subtitle")}</p>
      </div>

      {/* Stats */}
      {summary && (
        <div className="grid grid-cols-4 gap-3 mb-6">
          <StatCard label={t("pool.totalStrategies")} value={summary.total_strategies} icon={Layers} color="#f0b90b" />
          <StatCard label={t("pool.activeCount")} value={summary.active_count} icon={Zap} color="#00d4aa" />
          <StatCard label={t("pool.sleepingCount")} value={summary.sleeping_count} icon={Moon} color="#f59e0b" />
          <StatCard label={t("pool.avgSharpe")} value={summary.avg_sharpe?.toFixed(2)} icon={TrendingUp} color="#06b6d4" />
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Strategy Table */}
        <div className="card">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Zap size={14} /> {t("pool.activeCount")}
          </h3>
          <div className="text-xs">
            <div className="grid grid-cols-5 gap-2 pb-2 border-b border-dark-500 text-dark-400 mb-2">
              <span>Name</span><span>Type</span><span>Weight</span><span>Sharpe</span><span>Status</span>
            </div>
            {summary?.strategies?.map((s: Record<string, any>) => (
              <div key={s.id} className="grid grid-cols-5 gap-2 py-1.5 hover:bg-dark-600/50 rounded px-1 -mx-1 items-center">
                <span className="truncate">{s.name}</span>
                <span className="text-dark-400">{s.strategy_type}</span>
                <span>{(s.weight * 100).toFixed(1)}%</span>
                <span style={{ color: s.running_sharpe >= 0 ? "#00d4aa" : "#ef4444" }}>
                  {s.running_sharpe?.toFixed(2)}
                </span>
                <button
                  onClick={() => toggleStatus(s.id, s.status)}
                  className="px-2 py-0.5 rounded text-xs font-medium"
                  style={{ background: (STATUS_COLORS[s.status] || "#6b7280") + "20", color: STATUS_COLORS[s.status] }}
                >
                  {s.status}
                </button>
              </div>
            ))}
            {(!summary?.strategies?.length) && (
              <p className="text-dark-400 py-4 text-center">No strategies in pool</p>
            )}
          </div>
        </div>

        {/* Correlation Heatmap */}
        <div className="card">
          <h3 className="text-sm font-semibold mb-3">{t("pool.correlation")}</h3>
          {correlation?.labels?.length > 0 ? (
            <div>
              <div className="flex gap-1 mb-2">
                <div className="w-16" />
                {correlation?.labels?.map((l: string, i: number) => (
                  <div key={i} className="flex-1 text-center text-xs text-dark-400 truncate" title={l}>
                    {l.slice(0, 8)}
                  </div>
                ))}
              </div>
              {correlation?.matrix.map((row: number[], i: number) => (
                <div key={i} className="flex gap-1 mb-1">
                  <div className="w-16 text-xs text-dark-400 truncate" title={correlation.labels[i]}>
                    {correlation.labels[i].slice(0, 8)}
                  </div>
                  {row.map((v: number, j: number) => (
                    <div
                      key={j}
                      className="flex-1 text-center text-xs py-1.5 rounded font-mono"
                      style={{
                        background: v === 1 ? "#00d4aa20" : v > 0.5 ? "#ef444420" : v > 0 ? "#f59e0b20" : "#6b728020",
                        color: v === 1 ? "#00d4aa" : v > 0.5 ? "#ef4444" : v > 0 ? "#f59e0b" : "#6b7280",
                      }}
                    >
                      {v.toFixed(2)}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-dark-400 text-xs py-8 text-center">Need 2+ strategies for correlation</p>
          )}
        </div>
      </div>

      <button onClick={fetchData} className="mt-6 px-4 py-2 rounded-lg text-xs border border-dark-500 text-dark-400 hover:text-white flex items-center gap-2">
        <RefreshCw size={12} /> Refresh
      </button>
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color }: { label: string; value: string; icon: React.ComponentType<Record<string, any>>; color: string }) {
  return (
    <div className="card flex items-center gap-3">
      <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: color + "20" }}>
        <Icon size={16} style={{ color }} />
      </div>
      <div>
        <p className="text-dark-400 text-xs">{label}</p>
        <p className="text-lg font-bold">{value ?? "-"}</p>
      </div>
    </div>
  );
}
