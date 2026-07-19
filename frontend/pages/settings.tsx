import { useState, useEffect } from "react";
import { useLanguage } from "../lib/LanguageContext";
import { api } from "../lib/api";
import { Save, Key, Database, Shield, RefreshCw } from "lucide-react";

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState("");
  const [secret, setSecret] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [testnet, setTestnet] = useState(true);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [testResult, setTestResult] = useState<null | { ok: boolean; msg: string }>(null);
  const { t } = useLanguage();

  useEffect(() => {
    api.getExchangeSettings().then((data: any) => {
      if (data?.api_key) setApiKey(data.api_key);
      if (data?.has_secret) setSecret("***");
      if (data?.has_passphrase) setPassphrase("***");
      if (typeof data?.testnet === "boolean") setTestnet(data.testnet);
    }).catch(() => {});
  }, []);

  const saveSettings = async () => {
    setLoading(true);
    try {
      await api.saveExchangeSettings({ api_key: apiKey, secret, passphrase, testnet });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      console.error("Save failed", e);
    }
    setLoading(false);
  };

  const testConnection = async () => {
    setTestResult(null);
    try {
      const res = await api.testConnection({ api_key: apiKey, secret, passphrase, testnet });
      setTestResult({ ok: true, msg: "Connected! Latency: " + res.latency_ms + "ms" });
    } catch (e: any) {
      setTestResult({ ok: false, msg: e.message || "Connection failed" });
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div><h2 className="text-lg font-semibold text-white">{t("settings.title")}</h2><p className="text-xs text-dark-400 mt-1">{t("settings.subtitle")}</p></div>

      <div className="card">
        <div className="flex items-center gap-2 mb-4"><Key size={16} className="text-okx-yellow" /><h3 className="text-sm font-semibold text-white">{t("settings.api")}</h3></div>
        <div className="space-y-4">
          <div><label className="text-xs text-dark-400 block mb-1">{t("settings.apiKey")}</label><input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="Enter your OKX API key" className="w-full" /></div>
          <div><label className="text-xs text-dark-400 block mb-1">{t("settings.secret")}</label><input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="Enter your OKX secret key" className="w-full" /></div>
          <div><label className="text-xs text-dark-400 block mb-1">{t("settings.passphrase")}</label><input type="password" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} placeholder="Enter your OKX API passphrase" className="w-full" /></div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-dark-400">{t("settings.testnet")}</label>
            <button onClick={() => setTestnet(!testnet)} className={`w-10 h-5 rounded-full transition-colors relative ${testnet ? "bg-okx-green" : "bg-dark-700"}`}>
              <div className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-all ${testnet ? "left-5" : "left-0.5"}`} />
            </button>
            <span className="text-xs text-dark-400">{testnet ? t("settings.sandbox") : t("settings.live")}</span>
          </div>
          <div className="flex gap-3">
            <button onClick={saveSettings} disabled={loading} className="btn-primary flex items-center gap-2 text-sm">
              <Save size={16} /> {loading ? "Saving..." : saved ? t("settings.saved") : t("settings.save")}
            </button>
            <button onClick={testConnection} className="btn-ghost flex items-center gap-2 text-sm">
              <RefreshCw size={16} /> Test Connection
            </button>
          </div>
          {testResult && (
            <div className={`text-xs p-2 rounded ${testResult.ok ? "bg-okx-green/10 text-okx-green" : "bg-okx-red/10 text-okx-red"}`}>
              {testResult.msg}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="card"><div className="flex items-center gap-2 mb-2"><Database size={14} className="text-okx-blue" /><span className="text-xs font-semibold text-white">{t("settings.db")}</span></div><p className="text-xs text-dark-400">{t("settings.dbInfo")}</p><p className="text-xs text-dark-500 mt-1">{t("settings.dbDesc")}</p></div>
        <div className="card"><div className="flex items-center gap-2 mb-2"><Shield size={14} className="text-okx-green" /><span className="text-xs font-semibold text-white">{t("settings.risk")}</span></div><p className="text-xs text-dark-400">{t("settings.riskMax")}</p><p className="text-xs text-dark-500 mt-1">{t("settings.riskLoss")}</p></div>
      </div>

      <div className="card border-okx-green/20">
        <h3 className="text-sm font-semibold text-white mb-2">{t("settings.guide")}</h3>
        <ol className="text-xs text-dark-400 space-y-2 list-decimal list-inside">
          <li>{t("settings.guide1")} <span className="text-okx-blue">https://www.okx.com/account/my-api</span></li>
          <li>{t("settings.guide2")}</li>
          <li>{t("settings.guide3")}</li>
          <li>{t("settings.guide4")}</li>
          <li>{t("settings.guide5")}</li>
        </ol>
      </div>
    </div>
  );
}
