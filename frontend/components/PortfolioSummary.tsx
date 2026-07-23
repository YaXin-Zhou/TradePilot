import { useState, useEffect } from "react";
import {
  TrendingUp, TrendingDown, Wallet, Activity, DollarSign,
  BarChart3, RefreshCw
} from "lucide-react";
import { useLanguage } from "../lib/LanguageContext";
import { api } from "../lib/api";

interface PortfolioSummary {
  total_value_usdt: number;
  usdt_balance: number;
  btc_balance: number;
  btc_price: number;
  total_trades: number;
  total_pnl: number;
  active_strategies: number;
}

interface RealtimeAssets {
  total_assets_usdt: number;
  total_unrealized_pnl: number;
  total_pnl_pct: number;
  total_buy_cost: number;
  positions_value_usdt: number;
  weighted_24h_change_pct: number;
}

export default function PortfolioSummaryWidget({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [realtime, setRealtime] = useState<RealtimeAssets | null>(null);
  const { t } = useLanguage();

  useEffect(() => {
    api.getPortfolioSummary().then(setData).catch(() => {});
    api.getRealtimeAssets().then(setRealtime).catch(() => {});
  }, [refreshKey]);

  if (!data || !realtime) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="card animate-pulse h-24" />
        ))}
      </div>
    );
  }

  const formatUSD = (v: number) => "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const cards = [
    {
      label: t("dash.totalValue"),
      value: formatUSD(realtime.total_assets_usdt),
      sub: t("dash.usdtBalance") + ": " + formatUSD(data.usdt_balance),
      icon: DollarSign,
      color: "#00c076",
    },
    {
      label: t("dash.totalPnl"),
      value: (realtime.total_unrealized_pnl >= 0 ? "+" : "") + realtime.total_unrealized_pnl.toFixed(2) + " USDT",
      sub: (realtime.total_pnl_pct >= 0 ? "+" : "") + realtime.total_pnl_pct.toFixed(2) + "%",
      icon: realtime.total_unrealized_pnl >= 0 ? TrendingUp : TrendingDown,
      color: realtime.total_unrealized_pnl >= 0 ? "#00c076" : "#f6465d",
    },
    {
      label: t("dash.positionsValue"),
      value: formatUSD(realtime.positions_value_usdt),
      sub: "24h: " + (realtime.weighted_24h_change_pct >= 0 ? "+" : "") + realtime.weighted_24h_change_pct.toFixed(2) + "%",
      icon: Activity,
      color: realtime.weighted_24h_change_pct >= 0 ? "#00c076" : "#f6465d",
    },
    {
      label: t("dash.activeStrategies"),
      value: String(data.active_strategies),
      sub: data.total_trades + " " + t("dash.totalTrades"),
      icon: BarChart3,
      color: "#f0b90b",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div key={card.label} className="card hover:bg-dark-800/50 transition-colors">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-dark-400 font-medium uppercase tracking-wider">{card.label}</span>
            <card.icon size={18} style={{ color: card.color }} />
          </div>
          <div className="text-xl font-bold font-mono" style={{ color: card.color }}>
            {card.value}
          </div>
          <div className="text-xs text-dark-400 mt-1">{card.sub}</div>
        </div>
      ))}
    </div>
  );
}