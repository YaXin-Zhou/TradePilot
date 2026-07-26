import { useState, useEffect } from "react";
import { Shield, AlertTriangle, CheckCircle, Activity } from "lucide-react";
import { useLanguage } from "../lib/LanguageContext";
import { useMarketRegime, useKillSwitch } from "../lib/swr-config";
import { api } from "../lib/api";
import useSWR from "swr";
import Skeleton from "./Skeleton";

interface RiskPolicy {
  regime: string;
  max_position_pct: number;
  max_single_strategy_pct: number;
  max_daily_loss_pct: number;
  stop_loss_pct: number;
  trailing_stop_pct: number;
  min_sharpe_entry: number;
  max_correlation: number;
  time_stop_hours: number;
  atr_stop_multiplier: number;
  allowed_strategies: string[];
}

function useRiskPolicies() {
  return useSWR("risk-policies", () => api.getRiskPolicies() as Promise<Record<string, RiskPolicy>>, {
    refreshInterval: 30000,
    revalidateOnMount: true,
    keepPreviousData: true,
  });
}

export default function RiskDashboard() {
  const { t } = useLanguage();
  const { data: regime } = useMarketRegime();
  const { data: ks } = useKillSwitch();
  const { data: policies, isLoading } = useRiskPolicies();
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  if (!mounted || isLoading) return <Skeleton height={200} />;

  const currentRegime = regime?.regime || "unknown";
  const currentPolicy = policies?.[currentRegime] as RiskPolicy | undefined;

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-4">
        <Shield size={16} className="text-okx-yellow" />
        <span className="text-sm font-semibold text-white">{t("risk.title")}</span>
      </div>

      {/* Regime + KS status row */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3 rounded-lg bg-dark-800/50 border border-dark-700">
          <span className="text-xs text-dark-400">{t("dash.marketRegime")}</span>
          <p className="text-lg font-bold text-white mt-1">{currentRegime.toUpperCase()}</p>
        </div>
        <div className={`p-3 rounded-lg border ${ks?.status === "TRIGGERED" ? "border-red bg-red/10" : "border-dark-700 bg-dark-800/50"}`}>
          <span className="text-xs text-dark-400">Kill Switch</span>
          <p className={`text-lg font-bold mt-1 ${ks?.status === "TRIGGERED" ? "text-red" : "text-green"}`}>
            {ks?.status || "ARMED"}
          </p>
        </div>
      </div>

      {/* Policy details */}
      {currentPolicy ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Activity size={14} className="text-dark-400" />
            <span className="text-xs font-medium text-dark-300">
              {currentRegime.toUpperCase()} Regime Policy
            </span>
          </div>
          <div className="grid grid-cols-4 gap-2 text-xs">
            <div className="p-2 rounded bg-dark-800/50">
              <span className="text-dark-500">Max Pos</span>
              <p className="font-mono text-white mt-0.5">{(currentPolicy.max_position_pct * 100).toFixed(0)}%</p>
            </div>
            <div className="p-2 rounded bg-dark-800/50">
              <span className="text-dark-500">Daily Loss</span>
              <p className="font-mono text-white mt-0.5">{currentPolicy.max_daily_loss_pct}%</p>
            </div>
            <div className="p-2 rounded bg-dark-800/50">
              <span className="text-dark-500">Stop Loss</span>
              <p className="font-mono text-white mt-0.5">{currentPolicy.stop_loss_pct}%</p>
            </div>
            <div className="p-2 rounded bg-dark-800/50">
              <span className="text-dark-500">Trail</span>
              <p className="font-mono text-white mt-0.5">{currentPolicy.trailing_stop_pct}%</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="text-center py-4 text-dark-500 text-xs">
          {t("dash.noData")}
        </div>
      )}
    </div>
  );
}
