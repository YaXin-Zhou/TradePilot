import { useMemo, useState, useEffect } from "react";
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend
} from "recharts";
import { TrendingUp } from "lucide-react";
import { useLanguage } from "../lib/LanguageContext";
import { usePerformance } from "../lib/swr-config";
import Skeleton from "./Skeleton";

interface PnLPoint {
  date: string;
  pnl: number;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch {
    return iso.slice(0, 10);
  }
}

export default function EquityChart() {
  const { t } = useLanguage();
  const { data: perf, isLoading } = usePerformance();
  const [mounted, setMounted] = useState(false);

  // 首次渲染始终与 SSR 一致（Skeleton），避免 hydration mismatch
  useEffect(() => { setMounted(true); }, []);

  const chartData = useMemo(() => {
    if (!perf?.pnl_curve || perf.pnl_curve.length === 0) return null;
    const points: PnLPoint[] = perf.pnl_curve;
    let peak = 0;
    return points.map((p, i) => {
      peak = Math.max(peak, p.pnl);
      const dd = peak > 0 ? ((peak - p.pnl) / peak) * -100 : 0;
      return {
        date: formatDate(p.date),
        PnL: +(p.pnl.toFixed(2)),
        Drawdown: +dd.toFixed(1),
      };
    });
  }, [perf]);

  // mounted 为 false 时，始终渲染 Skeleton（与 SSR 输出一致）
  if (!mounted || isLoading) return <Skeleton height={280} />;

  if (!chartData) {
    return (
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp size={16} className="text-okx-green" />
          <span className="text-sm font-semibold text-white">{t("dash.equity")}</span>
        </div>
        <div className="h-[280px] flex items-center justify-center text-dark-500 text-sm">
          {t("dash.noData")}
        </div>
      </div>
    );
  }

  const pnlColor = perf.total_pnl >= 0 ? "#00c076" : "#f6465d";

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp size={16} className="text-okx-green" />
          <span className="text-sm font-semibold text-white">{t("dash.equity")}</span>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="text-dark-400">
            {t("dash.totalTrades")}: <b className="text-white">{perf.total_trades}</b>
          </span>
          <span className="text-dark-400">
            {t("dash.winRate")}: <b className="text-white">{perf.win_rate}%</b>
          </span>
          <span style={{ color: pnlColor }} className="font-mono font-semibold">
            {perf.total_pnl >= 0 ? "+" : ""}{perf.total_pnl?.toFixed(2)} USDT
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={chartData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
          <XAxis dataKey="date" tick={{ fill: "#737373", fontSize: 11 }} />
          <YAxis yAxisId="left" tick={{ fill: pnlColor, fontSize: 11 }} tickFormatter={(v) => v.toFixed(0)} />
          <YAxis yAxisId="right" orientation="right" tick={{ fill: "#f0b90b", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
          <Tooltip
            contentStyle={{ background: "#1a1a1a", border: "1px solid #2a2a2a", borderRadius: 6, fontSize: 12 }}
            labelStyle={{ color: "#eaecef" }}
          />
          <Legend />
          <Area yAxisId="left" type="monotone" dataKey="PnL" stroke={pnlColor} fill={pnlColor} fillOpacity={0.1} name="PnL (USDT)" />
          <Line yAxisId="right" type="monotone" dataKey="Drawdown" stroke="#f0b90b" dot={false} name="Drawdown %" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
