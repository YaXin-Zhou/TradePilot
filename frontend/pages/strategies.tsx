import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import { Plus, Play, Square, BarChart3, Trash2 } from "lucide-react";

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<any[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState("Grid Strategy");
  const [type, setType] = useState("grid");
  const [lower, setLower] = useState("83000");
  const [upper, setUpper] = useState("93000");
  const [grids, setGrids] = useState("20");
  const [amount, setAmount] = useState("100");
  const { t } = useLanguage();

  const load = () => api.listStrategies().then(setStrategies).catch(() => {});
  useEffect(() => { load(); }, []);

  const createStrategy = async () => {
    await api.createStrategy({ name, type, symbol: "BTC/USDT", config: { lower_bound: parseFloat(lower), upper_bound: parseFloat(upper), grid_count: parseInt(grids), order_amount: parseFloat(amount) } });
    setShowNew(false);
    load();
  };

  const toggleStrategy = async (s: any) => {
    await api.updateStrategy(s.id, { status: s.status === "running" ? "stopped" : "running" });
    load();
  };

  const deleteStrategy = async (id: string) => { await api.deleteStrategy(id); load(); };

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
        {strategies.map((s) => (
          <div key={s.id} className="card hover:border-dark-700 transition-colors">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className={`w-2 h-2 rounded-full ${s.status === "running" ? "bg-okx-green" : s.status === "paused" ? "bg-okx-yellow" : "bg-dark-500"}`} />
                <div>
                  <span className="text-sm font-semibold text-white">{s.name}</span>
                  <span className="ml-2 text-xs px-2 py-0.5 rounded bg-dark-800 text-dark-400">{s.type}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
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
        ))}
      </div>
    </div>
  );
}

