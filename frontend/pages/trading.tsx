import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import type { ApiResponse } from "../types/api";
import { TrendingUp, TrendingDown, AlertCircle, RefreshCw, Shield, ChevronDown, ChevronUp, Check } from "lucide-react";

interface ManualRisk {
  max_order_usdt: number;
  max_daily_loss_usdt: number;
  min_order_usdt: number;
  max_position_usdt: number;
  enabled: boolean;
}

export default function TradingPage() {
  const [ticker, setTicker] = useState<Record<string, any> | null>(null);
  const [balance, setBalance] = useState<Record<string, any> | null>(null);
  const [orders, setOrders] = useState<any[]>([]);
  const [side, setSide] = useState("buy");
  const [amount, setAmount] = useState("");
  const [price, setPrice] = useState("");
  const [status, setStatus] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const { t, lang } = useLanguage();

  // 手动风控设置
  const [riskOpen, setRiskOpen] = useState(false);
  const [risk, setRisk] = useState<ManualRisk>({
    max_order_usdt: 0, max_daily_loss_usdt: 0,
    min_order_usdt: 0, max_position_usdt: 0, enabled: false,
  });
  const [riskSaving, setRiskSaving] = useState(false);
  const [riskToast, setRiskToast] = useState("");

  const isZh = lang === "zh";

  useEffect(() => {
    api.getTicker().then(setTicker).catch(() => {});
    api.getBalance().then(setBalance).catch(() => {});
    api.getOpenOrders().then(setOrders).catch(() => {});
    api.getManualRiskSettings().then((r: ManualRisk) => {
      setRisk(r);  // v2.0: request() 已解包 json.data，无需再判 success/data
    }).catch(() => {});
  }, [refreshKey]);

  const handleSubmit = async () => {
    setStatus(isZh ? "下单中..." : "Placing...");
    try {
      await api.placeLimitOrder({ symbol: "BTC/USDT", side, amount: parseFloat(amount), price: parseFloat(price || ticker?.last || "0") });
      setStatus(isZh ? "已提交" : "Placed");
      setRefreshKey((k) => k + 1);
    } catch (e: unknown) {
      setStatus(`${isZh ? "错误" : "Error"}: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const saveRisk = async () => {
    setRiskSaving(true);
    try {
      const r: ManualRisk = await api.updateManualRiskSettings(risk as unknown as Record<string, unknown>);
      setRisk(r);  // v2.0: request() 已解包 json.data
      setRiskToast(isZh ? "风控设置已保存" : "Risk settings saved");
      setTimeout(() => setRiskToast(""), 2000);
    } catch {}
    setRiskSaving(false);
  };

  const updateRisk = (key: keyof ManualRisk, val: number | boolean) => {
    setRisk((prev) => ({ ...prev, [key]: val }));
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Order Form */}
      <div className="card lg:col-span-1 space-y-0">
        <h3 className="text-sm font-semibold text-white mb-4">{t("trade.placeOrder")}</h3>
        <div className="flex rounded-lg overflow-hidden border border-dark-800 mb-4">
          <button
            onClick={() => setSide("buy")}
            className={`flex-1 py-2 text-sm font-medium transition-all ${side === "buy" ? "bg-okx-green text-black" : "bg-dark-900 text-dark-400"}`}
          >{t("trade.buy")}</button>
          <button
            onClick={() => setSide("sell")}
            className={`flex-1 py-2 text-sm font-medium transition-all ${side === "sell" ? "bg-okx-red text-white" : "bg-dark-900 text-dark-400"}`}
          >{t("trade.sell")}</button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-dark-400 mb-1 block">{t("trade.price")}</label>
            <input type="number" value={price} onChange={(e) => setPrice(e.target.value)} placeholder={ticker?.last?.toFixed(2) || t("trade.auto")} className="w-full" />
          </div>
          <div>
            <label className="text-xs text-dark-400 mb-1 block">{t("trade.amount")}</label>
            <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.001" step="0.001" className="w-full" />
          </div>
          <div>
            <label className="text-xs text-dark-400 mb-1 block">{t("trade.total")}</label>
            <input type="number" value={amount && (price || ticker?.last) ? (parseFloat(amount) * parseFloat(price || ticker?.last)).toFixed(2) : ""} disabled className="w-full opacity-60" />
          </div>
          <button
            onClick={handleSubmit}
            className={`w-full py-3 rounded-lg font-semibold text-sm transition-all ${side === "buy" ? "bg-okx-green text-black hover:opacity-85" : "bg-okx-red text-white hover:opacity-85"}`}
          >{side === "buy" ? t("settings.buyBtc") : t("settings.sellBtc")}</button>
          {status && <div className="flex items-center gap-2 text-xs text-dark-400 mt-2"><AlertCircle size={12} />{status}</div>}
        </div>
        {balance && (
          <div className="mt-4 pt-4 border-t border-dark-800 space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-dark-400">{t("trade.usdtAvail")}</span>
              <span className="text-dark-200 font-mono">{(balance.USDT?.free || 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-dark-400">{t("trade.btcAvail")}</span>
              <span className="text-dark-200 font-mono">{(balance.BTC?.free || 0).toFixed(6)}</span>
            </div>
          </div>
        )}

        {/* ──── 手动交易风控设置 ──── */}
        <div className="mt-4 pt-4 border-t border-dark-800">
          <button
            onClick={() => setRiskOpen(!riskOpen)}
            className="flex items-center justify-between w-full text-xs text-dark-400 hover:text-dark-200 transition-colors"
          >
            <span className="flex items-center gap-2">
              <Shield size={14} className={risk.enabled ? "text-yellow-400" : "text-dark-500"} />
              {isZh ? "手动交易风控" : "Manual Risk Control"}
              {risk.enabled && (
                <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
              )}
            </span>
            {riskOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {riskOpen && (
            <div className="mt-3 space-y-3 text-xs animate-fadeIn">
              {/* 启用开关 */}
              <div className="flex items-center justify-between py-1.5">
                <span className="text-dark-400">{isZh ? "启用风控" : "Enable Risk"}</span>
                <button
                  onClick={() => updateRisk("enabled", !risk.enabled)}
                  className={`w-9 h-5 rounded-full transition-colors relative ${risk.enabled ? "bg-yellow-500" : "bg-dark-600"}`}
                >
                  <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${risk.enabled ? "translate-x-4" : "translate-x-0.5"}`} />
                </button>
              </div>

              {risk.enabled && (
                <>
                  <div>
                    <label className="text-dark-500 mb-1 block">
                      {isZh ? "最大单笔金额 (USDT)" : "Max Order (USDT)"}
                      <span className="text-dark-600 ml-1">{isZh ? "(0=不限)" : "(0=unlimited)"}</span>
                    </label>
                    <input
                      type="number" min={0} step={100}
                      value={risk.max_order_usdt || ""}
                      onChange={(e) => updateRisk("max_order_usdt", parseFloat(e.target.value) || 0)}
                      className="w-full text-xs py-1.5" placeholder="10000"
                    />
                  </div>
                  <div>
                    <label className="text-dark-500 mb-1 block">
                      {isZh ? "最小单笔金额 (USDT)" : "Min Order (USDT)"}
                      <span className="text-dark-600 ml-1">{isZh ? "(0=不限)" : "(0=unlimited)"}</span>
                    </label>
                    <input
                      type="number" min={0} step={10}
                      value={risk.min_order_usdt || ""}
                      onChange={(e) => updateRisk("min_order_usdt", parseFloat(e.target.value) || 0)}
                      className="w-full text-xs py-1.5" placeholder="10"
                    />
                  </div>
                  <div>
                    <label className="text-dark-500 mb-1 block">
                      {isZh ? "日亏损上限 (USDT)" : "Daily Loss Limit (USDT)"}
                      <span className="text-dark-600 ml-1">{isZh ? "(0=不限)" : "(0=unlimited)"}</span>
                    </label>
                    <input
                      type="number" min={0} step={100}
                      value={risk.max_daily_loss_usdt || ""}
                      onChange={(e) => updateRisk("max_daily_loss_usdt", parseFloat(e.target.value) || 0)}
                      className="w-full text-xs py-1.5" placeholder="500"
                    />
                  </div>

                  {riskToast && (
                    <div className="px-3 py-2 bg-green-500/10 border border-green-500/30 rounded text-green-400 flex items-center gap-1.5">
                      <Check size={12} /> {riskToast}
                    </div>
                  )}
                  <button
                    onClick={saveRisk}
                    disabled={riskSaving}
                    className="w-full py-2 rounded-lg text-xs font-medium bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 hover:bg-yellow-500/30 transition-all disabled:opacity-50"
                  >
                    {riskSaving ? (isZh ? "保存中..." : "Saving...") : (isZh ? "保存风控设置" : "Save Risk Settings")}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Open Orders & Market Info */}
      <div className="lg:col-span-2 space-y-4">
        {ticker && (
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: t("trade.lastPrice"), value: `$${ticker.last?.toFixed(2)}`, color: ticker.change_pct >= 0 ? "text-green" : "text-red" },
              { label: t("trade.change24h"), value: `${ticker.change_pct >= 0 ? "+" : ""}${ticker.change_pct?.toFixed(2)}%`, color: ticker.change_pct >= 0 ? "text-green" : "text-red" },
              { label: t("trade.high24h"), value: `$${ticker.high?.toFixed(2)}`, color: "text-dark-200" },
              { label: t("trade.low24h"), value: `$${ticker.low?.toFixed(2)}`, color: "text-dark-200" },
            ].map((item) => (
              <div key={item.label} className="card py-3">
                <div className="text-xs text-dark-400 mb-1">{item.label}</div>
                <div className={`text-sm font-bold font-mono ${item.color}`}>{item.value}</div>
              </div>
            ))}
          </div>
        )}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white">{t("trade.openOrders")}</h3>
            <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost text-xs py-1 px-3"><RefreshCw size={12} /></button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-dark-400 border-b border-dark-800">
                  <th className="text-left py-2">{t("trade.side")}</th>
                  <th className="text-right px-2 py-2">{t("trade.price")}</th>
                  <th className="text-right px-2 py-2">{t("trade.amount")}</th>
                  <th className="text-right px-2 py-2">{t("trade.filled")}</th>
                  <th className="text-right py-2">{t("trade.status")}</th>
                </tr>
              </thead>
              <tbody>
                {orders.length === 0 && (
                  <tr><td colSpan={5} className="text-center py-8 text-dark-500">{t("trade.noOrders")}</td></tr>
                )}
                {orders.map((o) => (
                  <tr key={o.id} className="border-b border-dark-800/50">
                    <td className={`py-2.5 font-medium ${o.side === "buy" ? "text-green" : "text-red"}`}>{o.side?.toUpperCase()}</td>
                    <td className="text-right px-2 py-2 font-mono">${o.price?.toFixed(2)}</td>
                    <td className="text-right px-2 py-2 font-mono">{o.amount?.toFixed(6)}</td>
                    <td className="text-right px-2 py-2 font-mono">{o.filled?.toFixed(6)}</td>
                    <td className="text-right py-2 text-dark-400">{o.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
