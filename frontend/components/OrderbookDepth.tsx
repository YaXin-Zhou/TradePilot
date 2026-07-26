import { useMemo, useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { Layers, ChevronDown, ChevronUp } from "lucide-react";
import { useLanguage } from "../lib/LanguageContext";
import useSWR from "swr";
import { api } from "../lib/api";
import Skeleton from "./Skeleton";

function useOrderbook(symbol: string) {
  return useSWR(`orderbook:${symbol}`, () => api.getOrderbook(symbol), {
    refreshInterval: 5000,
    revalidateOnMount: true,
    keepPreviousData: true,
  });
}

export default function OrderbookDepth({ symbol = "BTC/USDT" }: { symbol?: string }) {
  const { t } = useLanguage();
  const { data, isLoading } = useOrderbook(symbol);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  const chartData = useMemo(() => {
    if (!data) return null;
    const bids = (data.bids || []).map(([price, size]: [number, number]) => ({
      price: +price.toFixed(1),
      size: +size.toFixed(4),
      side: "bid" as const,
    })).slice(0, 15);
    const asks = (data.asks || []).map(([price, size]: [number, number]) => ({
      price: +price.toFixed(1),
      size: +size.toFixed(4),
      side: "ask" as const,
    })).reverse().slice(0, 15);
    return [...asks, ...bids];
  }, [data]);

  if (!mounted || isLoading) return <Skeleton height={300} />;
  if (!chartData) return null;

  const midPrice = data?.asks?.[0]?.[0] || 0;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Layers size={16} className="text-okx-blue" />
          <span className="text-sm font-semibold text-white">{t("trading.orderbook")}</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-dark-400">{symbol}</span>
          {midPrice > 0 && <span className="font-mono text-white">{midPrice.toFixed(1)}</span>}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
          barCategoryGap={1}>
          <CartesianGrid strokeDasharray="3 3" stroke="#262626" horizontal={false} />
          <XAxis type="number" tick={{ fill: "#737373", fontSize: 10 }} />
          <YAxis type="number" dataKey="price" tick={{ fill: "#737373", fontSize: 10 }} domain={["auto", "auto"]} />
          <Tooltip contentStyle={{ background: "#1a1a1a", border: "1px solid #2a2a2a", fontSize: 12 }} />
          <Bar dataKey="size" radius={[0, 2, 2, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.side === "bid" ? "#00c076" : "#f6465d"} fillOpacity={0.6} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
