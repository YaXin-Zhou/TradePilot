import { useState, useEffect } from "react";
import { useLanguage } from "../lib/LanguageContext";
import { api } from "../lib/api";
import { Save, Key, Database, Shield, RefreshCw, FlaskConical, AlertTriangle, CheckCircle2, Power } from "lucide-react";

type Mode = "testnet" | "live";

interface CredStatus {
  api_key: string;
  has_key: boolean;
  has_secret: boolean;
  has_passphrase: boolean;
}

interface ExchangeSettingsData {
  active: Mode;
  testnet: CredStatus;
  live: CredStatus;
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Mode>("testnet");
  const [settingsData, setSettingsData] = useState<ExchangeSettingsData | null>(null);

  // 两套独立的输入状态
  const [testnetForm, setTestnetForm] = useState({ api_key: "", secret: "", passphrase: "" });
  const [liveForm, setLiveForm] = useState({ api_key: "", secret: "", passphrase: "" });

  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<null | { ok: boolean; msg: string }>(null);
  const [switching, setSwitching] = useState(false);
  const [switchMsg, setSwitchMsg] = useState<null | { ok: boolean; msg: string }>(null);
  const { t } = useLanguage();

  const loadSettings = async () => {
    try {
      const data: ExchangeSettingsData = await api.getExchangeSettings();
      setSettingsData(data);
      // 已配置的显示脱敏值占位
      if (data.testnet?.has_key) setTestnetForm((f) => ({ ...f, api_key: data.testnet.api_key }));
      if (data.live?.has_key) setLiveForm((f) => ({ ...f, api_key: data.live.api_key }));
      // 默认显示当前激活的标签页
      setActiveTab(data.active);
    } catch (e) {
      console.error("Load settings failed", e);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const currentForm = activeTab === "testnet" ? testnetForm : liveForm;
  const setCurrentForm = activeTab === "testnet" ? setTestnetForm : setLiveForm;
  const currentStatus = settingsData ? settingsData[activeTab] : null;
  const isActive = settingsData?.active === activeTab;

  const saveSettings = async () => {
    setSaving(true);
    setSavedMsg(null);
    try {
      const res: any = await api.saveExchangeSettings({
        mode: activeTab,
        api_key: currentForm.api_key,
        secret: currentForm.secret,
        passphrase: currentForm.passphrase,
      });
      setSavedMsg(res?.verify_msg || t("settings.saved"));
      await loadSettings();
    } catch (e: any) {
      setSavedMsg(null);
      setTestResult({ ok: false, msg: e.message || "Save failed" });
    }
    setSaving(false);
    setTimeout(() => setSavedMsg(null), 3000);
  };

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res: any = await api.testConnection({
        mode: activeTab,
        api_key: currentForm.api_key,
        secret: currentForm.secret,
        passphrase: currentForm.passphrase,
      });
      setTestResult({ ok: res.success !== false, msg: res?.data?.message || res?.error || (res.success ? t("settings.testOk") : "Failed") });
    } catch (e: any) {
      setTestResult({ ok: false, msg: e.message || "Connection failed" });
    }
    setTesting(false);
  };

  const switchMode = async () => {
    if (activeTab === "live") {
      const confirmed = window.confirm(t("settings.switchConfirm"));
      if (!confirmed) return;
    }
    setSwitching(true);
    setSwitchMsg(null);
    try {
      const res: any = await api.switchExchangeMode({ mode: activeTab, confirm: activeTab === "live" });
      if (res.success === false) {
        setSwitchMsg({ ok: false, msg: res.error || "Switch failed" });
      } else {
        setSwitchMsg({ ok: true, msg: `${t("settings.switchOk")} → ${res?.data?.mode_label || activeTab}` });
        await loadSettings();
      }
    } catch (e: any) {
      setSwitchMsg({ ok: false, msg: e.message || "Switch failed" });
    }
    setSwitching(false);
    setTimeout(() => setSwitchMsg(null), 4000);
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold text-white">{t("settings.title")}</h2>
        <p className="text-xs text-dark-400 mt-1">{t("settings.subtitle")}</p>
        {settingsData && (
          <div className="mt-2 inline-flex items-center gap-2 text-xs">
            <span className="text-dark-400">{t("settings.activeMode")}:</span>
            <span className={`px-2 py-0.5 rounded-full font-semibold ${settingsData.active === "testnet" ? "bg-okx-green/20 text-okx-green" : "bg-okx-red/20 text-okx-red"}`}>
              {settingsData.active === "testnet" ? t("settings.modeTestnet") : t("settings.modeLive")}
            </span>
          </div>
        )}
      </div>

      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Key size={16} className="text-okx-yellow" />
          <h3 className="text-sm font-semibold text-white">{t("settings.api")}</h3>
        </div>

        {/* 标签页切换 */}
        <div className="flex gap-1 mb-4 p-1 bg-dark-800 rounded-lg">
          <button
            onClick={() => { setActiveTab("testnet"); setTestResult(null); setSavedMsg(null); setSwitchMsg(null); }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-md text-xs font-medium transition-colors ${activeTab === "testnet" ? "bg-okx-green/20 text-okx-green" : "text-dark-400 hover:text-white"}`}
          >
            <FlaskConical size={13} /> {t("settings.testnetTab")}
            {settingsData?.testnet?.has_key && <CheckCircle2 size={12} className="opacity-70" />}
          </button>
          <button
            onClick={() => { setActiveTab("live"); setTestResult(null); setSavedMsg(null); setSwitchMsg(null); }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-md text-xs font-medium transition-colors ${activeTab === "live" ? "bg-okx-red/20 text-okx-red" : "text-dark-400 hover:text-white"}`}
          >
            <AlertTriangle size={13} /> {t("settings.liveTab")}
            {settingsData?.live?.has_key && <CheckCircle2 size={12} className="opacity-70" />}
          </button>
        </div>

        {/* 实盘警告横幅 */}
        {activeTab === "live" && (
          <div className="mb-4 p-2.5 rounded bg-okx-red/10 border border-okx-red/30 flex items-start gap-2">
            <AlertTriangle size={14} className="text-okx-red flex-shrink-0 mt-0.5" />
            <p className="text-xs text-okx-red">{t("settings.liveWarning")}</p>
          </div>
        )}

        {/* 当前模式状态条 */}
        {currentStatus && (
          <div className="mb-4 flex items-center gap-2 text-xs">
            <span className="text-dark-400">{activeTab === "testnet" ? t("settings.modeTestnet") : t("settings.modeLive")}:</span>
            <span className={currentStatus.has_key ? "text-okx-green" : "text-dark-500"}>
              {currentStatus.has_key ? t("settings.configured") : t("settings.noKey")}
            </span>
            {isActive && (
              <span className="px-1.5 py-0.5 rounded bg-okx-blue/20 text-okx-blue text-[10px] font-semibold">{t("settings.activeMode")}</span>
            )}
          </div>
        )}

        {/* 输入表单 */}
        <div className="space-y-4">
          <div>
            <label className="text-xs text-dark-400 block mb-1">{t("settings.apiKey")}</label>
            <input
              type="password"
              value={currentForm.api_key}
              onChange={(e) => setCurrentForm({ ...currentForm, api_key: e.target.value })}
              placeholder={currentStatus?.has_key ? currentStatus.api_key : `Enter ${activeTab === "testnet" ? "testnet" : "live"} API key`}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-xs text-dark-400 block mb-1">{t("settings.secret")}</label>
            <input
              type="password"
              value={currentForm.secret}
              onChange={(e) => setCurrentForm({ ...currentForm, secret: e.target.value })}
              placeholder={currentStatus?.has_secret ? "••••••••（已保存，输入新值覆盖）" : "Enter secret key"}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-xs text-dark-400 block mb-1">{t("settings.passphrase")}</label>
            <input
              type="password"
              value={currentForm.passphrase}
              onChange={(e) => setCurrentForm({ ...currentForm, passphrase: e.target.value })}
              placeholder={currentStatus?.has_passphrase ? "••••••••（已保存，输入新值覆盖）" : "Enter passphrase"}
              className="w-full"
            />
          </div>

          {/* 操作按钮 */}
          <div className="flex flex-wrap gap-2">
            <button onClick={saveSettings} disabled={saving} className="btn-primary flex items-center gap-2 text-sm">
              <Save size={15} /> {saving ? "..." : savedMsg === t("settings.saved") ? t("settings.saved") : t("settings.save")}
            </button>
            <button onClick={testConnection} disabled={testing} className="btn-ghost flex items-center gap-2 text-sm">
              <RefreshCw size={15} className={testing ? "animate-spin" : ""} /> {t("settings.testConn")}
            </button>
            {!isActive && currentStatus?.has_key && (
              <button
                onClick={switchMode}
                disabled={switching}
                className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg transition-colors ${activeTab === "live" ? "bg-okx-red/20 text-okx-red hover:bg-okx-red/30" : "bg-okx-green/20 text-okx-green hover:bg-okx-green/30"}`}
              >
                <Power size={15} /> {t("settings.activate")}
              </button>
            )}
          </div>

          {/* 反馈消息 */}
          {savedMsg && (
            <div className="text-xs p-2 rounded bg-okx-green/10 text-okx-green">{savedMsg}</div>
          )}
          {testResult && (
            <div className={`text-xs p-2 rounded ${testResult.ok ? "bg-okx-green/10 text-okx-green" : "bg-okx-red/10 text-okx-red"}`}>
              {testResult.msg}
            </div>
          )}
          {switchMsg && (
            <div className={`text-xs p-2 rounded ${switchMsg.ok ? "bg-okx-blue/10 text-okx-blue" : "bg-okx-red/10 text-okx-red"}`}>
              {switchMsg.msg}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <Database size={14} className="text-okx-blue" />
            <span className="text-xs font-semibold text-white">{t("settings.db")}</span>
          </div>
          <p className="text-xs text-dark-400">{t("settings.dbInfo")}</p>
          <p className="text-xs text-dark-500 mt-1">{t("settings.dbDesc")}</p>
        </div>
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <Shield size={14} className="text-okx-green" />
            <span className="text-xs font-semibold text-white">{t("settings.risk")}</span>
          </div>
          <p className="text-xs text-dark-400">{t("settings.riskMax")}</p>
          <p className="text-xs text-dark-500 mt-1">{t("settings.riskLoss")}</p>
        </div>
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
