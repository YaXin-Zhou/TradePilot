import { useState, useMemo } from "react";
import { BarChart3, TrendingUp, TrendingDown, Minus, ShieldAlert } from "lucide-react";
import { useLanguage } from "../lib/LanguageContext";
import { useStrategies } from "../lib/swr-config";
import Skeleton from "./Skeleton";

type SortKey = "sharpe" | "win" | "maxdd" | "pnl";

export default function StrategyComparison() {
  const { t } = useLanguage();
  const { data: strategies, isLoading } = useStrategies();
  const [sortKey, setSortKey] = useState<SortKey>("sharpe");

  const sorted = useMemo(() => {
    if (!strategies || strategies.length === 0) return null;
    const arr = [...strategies];
    arr.sort((a, b) => {
      const va = sortKey === "sharpe" ? (a.sharpe_ratio || 0) :
                 sortKey === "win" ? (a.win_rate || 0) :
                 sortKey === "maxdd" ? -(a.max_drawdown || 0) :
                 (a.total_pnl || 0);
      const vb = sortKey === "sharpe" ? (b.sharpe_ratio || 0) :
                 sortKey === "win" ? (b.win_rate || 0) :
                 sortKey === "maxdd" ? -(b.max_drawdown || 0) :
                 (b.total_pnl || 0);
      return vb - va;
    });
    return arr;
  }, [strategies, sortKey]);

  if (isLoading) return <Skeleton height={200} />;
  if (!sorted || sorted.length === 0) return null;

  const active = sorted.filter((s) => s.status !== "draft");
  const best = active.length > 0 ? active[0] : null;

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 size={16} className="text-okx-blue" />
        <span className="text-sm font-semibold text-white">{t("strat.compare")}</span>
        <span className="text-xs text-dark-400 ml-auto">
          {sorted.length} {t("strat.strategies")}
        </span>
      </div>

      {/* Best performer highlight */}
      {best && (
        <div className="mb-4 p-3 rounded-lg bg-dark-800/50 border border-dark-700 flex items-center justify-between">
          <div>
            <span className="text-xs text-dark-400">{t("strat.bestPerf")}</span>
            <span className="ml-2 text-sm font-semibold text-okx-green">{best.name}</span>
            <span className="ml-2 text-xs text-dark-500">({best.type})</span>
          </div>
          <div className="flex gap-4 text-xs">
            <span className="text-dark-400">Sharpe <b className="text-white">{best.sharpe_ratio?.toFixed(2) || "-"}</b></span>
            <span className="text-dark-400">Win <b className="text-white">{best.win_rate ? `${(best.win_rate * 100).toFixed(1)}%` : "-"}</b></span>
          </div>
        </div>
      )}

      {/* Sortable table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-dark-400 border-b border-dark-800">
              <th className="text-left py-2">{t("strat.name")}</th>
              <th className="text-left py-2">{t("strat.type")}</th>
              <th className="text-right py-2 cursor-pointer hover:text-white" onClick={() => setSortKey("sharpe")}>
                Sharpe {sortKey === "sharpe" ? "▼" : ""}
              </th>
              <th className="text-right py-2 cursor-pointer hover:text-white" onClick={() => setSortKey("win")}>
                {t("strat.winRate")} {sortKey === "win" ? "▼" : ""}
              </th>
              <th className="text-right py-2 cursor-pointer hover:text-white" onClick={() => setSortKey("maxdd")}>
                Max DD {sortKey === "maxdd" ? "▼" : ""}
              </th>
              <th className="text-right py-2 cursor-pointer hover:text-white" onClick={() => setSortKey("pnl")}>
                PnL {sortKey === "pnl" ? "▼" : ""}
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s, i) => {
              const pnl = s.total_pnl || 0;
              const sharpe = s.sharpe_ratio || 0;
              return (
                <tr key={s.id} className={`border-b border-dark-800/50 hover:bg-dark-800/30 ${i === 0 ? "bg-dark-800/20" : ""}`}>
                  <td className="py-2 font-medium text-dark-200">{s.name}</td>
                  <td className="py-2 text-dark-400">{s.type}</td>
                  <td className={`text-right py-2 font-mono ${sharpe >= 1 ? "text-green" : sharpe >= 0 ? "text-dark-200" : "text-red"}`}>
                    {sharpe.toFixed(2)}
                  </td>
                  <td className="text-right py-2 font-mono text-dark-200">
                    {s.win_rate ? `${(s.win_rate * 100).toFixed(1)}%` : "-"}
                  </td>
                  <td className={`text-right py-2 font-mono ${(s.max_drawdown || 0) > 0.3 ? "text-red" : "text-dark-200"}`}>
                    {s.max_drawdown ? `${(s.max_drawdown * 100).toFixed(1)}%` : "-"}
                  </td>
                  <td className={`text-right py-2 font-mono ${pnl >= 0 ? "text-green" : "text-red"}`}>
                    {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
