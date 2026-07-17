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

export default function PortfolioSummaryWidget({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const { t } = useLanguage();

  useEffect(() => {
    api.getPortfolioSummary().then(setData).catch(() => {});
  }, [refreshKey]);

  if (!data) {
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
      value: formatUSD(data.total_value_usdt),
      sub: "BTC: " + data.btc_balance.toFixed(6),
      icon: DollarSign,
      color: "#00c076",
    },
    {
      label: t("dash.usdtBalance"),
      value: formatUSD(data.usdt_balance),
      sub: "BTC Price: " + formatUSD(data.btc_price),
      icon: Wallet,
      color: "#1e80ff",
    },
    {
      label: t("dash.totalPnl"),
      value: (data.total_pnl >= 0 ? "+" : "") + data.total_pnl.toFixed(4) + " USDT",
      sub: data.total_trades + " " + t("dash.tradesDone"),
      icon: data.total_pnl >= 0 ? TrendingUp : TrendingDown,
      color: data.total_pnl >= 0 ? "#00c076" : "#f6465d",
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