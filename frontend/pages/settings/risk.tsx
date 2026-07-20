import { useState, useEffect } from "react";
import { useLanguage } from "../../lib/LanguageContext";
import { api } from "@/lib/api";
import { Shield, Save, RotateCcw, Check, AlertTriangle } from "lucide-react";

const REGIMES = ["TRENDING_UP", "TRENDING_DOWN", "RANGING_HIGH_VOL", "RANGING_LOW_VOL"];
const STRATEGY_TYPES = [
  { value: "ma_cross", label: "MA Cross" },
  { value: "rsi", label: "RSI" },
  { value: "bollinger", label: "Bollinger" },
  { value: "grid", label: "Grid" },
  { value: "ai_generated", label: "AI Generated" },
];

export default function RiskSettingsPage() {
  const { t, lang } = useLanguage();
  const [policies, setPolicies] = useState<Record<string, any>>({});
  const [activeRegime, setActiveRegime] = useState("TRENDING_UP");
  const [editing, setEditing] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    api.getRiskPolicies().then((r: Record<string, any>) => {
      if (r.success) {
        setPolicies(r.data);
        setEditing(r.data);
      }
    });
  }, []);

  function updateField(field: string, value: unknown) {
    setEditing((prev: Record<string, any>) => ({
      ...prev,
      [activeRegime]: { ...prev[activeRegime], [field]: value },
    }));
  }

  function toggleStrategy(type: string) {
    const current: string[] = editing[activeRegime]?.allowed_strategies || [];
    const next = current.includes(type)
      ? current.filter((s: string) => s !== type)
      : [...current, type];
    updateField("allowed_strategies", next);
  }

  async function saveRegime() {
    setSaving(true);
    try {
      const r = await api.updateRiskPolicy({
        regime: activeRegime,
        ...editing[activeRegime],
      });
      if (r.success) {
        setPolicies((prev: Record<string, any>) => ({ ...prev, [activeRegime]: r.data }));
        setToast(t("risk.saved"));
        setTimeout(() => setToast(""), 2000);
      }
    } catch {}
    setSaving(false);
  }

  async function resetAll() {
    setSaving(true);
    try {
      const r = await api.resetRiskPolicies();
      if (r.success) {
        setPolicies(r.data);
        setEditing(r.data);
        setToast(t("risk.resetDone"));
        setTimeout(() => setToast(""), 2000);
      }
    } catch {}
    setSaving(false);
  }

  const regimeColor = (regime: string) => {
    const m: Record<string, string> = {
      TRENDING_UP: "#00d4aa", TRENDING_DOWN: "#ef4444",
      RANGING_HIGH_VOL: "#f59e0b", RANGING_LOW_VOL: "#6b7280",
    };
    return m[regime] || "#6b7280";
  };

  const policy = editing[activeRegime] || {};

  return (
    <div className="page-container">
      <div className="mb-6">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <Shield size={22} /> {t("risk.title")}
        </h1>
        <p className="text-dark-400 text-sm mt-1">{t("risk.subtitle")}</p>
      </div>

      {toast && (
        <div className="mb-4 px-4 py-2 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-sm flex items-center gap-2">
          <Check size={14} /> {toast}
        </div>
      )}

      {/* Regime Tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {REGIMES.map((r) => (
            <button
              key={r}
              onClick={() => setActiveRegime(r)}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-all"
              style={{
                background: activeRegime === r ? `${regimeColor(r)}20` : "transparent",
                border: `1px solid ${activeRegime === r ? regimeColor(r) : "var(--dark-500)"}`,
                color: activeRegime === r ? regimeColor(r) : "var(--dark-400)",
              }}
            >
              {t(`risk.regimeLabel.${r}`)}
            </button>
          ))}
      </div>

      {/* Policy Editor */}
      <div className="grid grid-cols-2 gap-4">
        <NumberField label={t("risk.maxPosition")} value={policy.max_position_pct} field="max_position_pct" suffix="%" step={0.05} update={updateField} />
        <NumberField label={t("risk.singleStrategy")} value={policy.max_single_strategy_pct} field="max_single_strategy_pct" suffix="%" step={0.05} update={updateField} />
        <NumberField label={t("risk.dailyLossLimit")} value={policy.max_daily_loss_pct} field="max_daily_loss_pct" suffix="%" step={0.5} update={updateField} />
        <NumberField label={t("risk.stopLoss")} value={policy.stop_loss_pct} field="stop_loss_pct" suffix="%" step={0.5} update={updateField} />
        <NumberField label={t("risk.trailingStop")} value={policy.trailing_stop_pct} field="trailing_stop_pct" suffix="%" step={0.5} update={updateField} />
        <NumberField label={t("risk.minSharpe")} value={policy.min_sharpe_entry} field="min_sharpe_entry" suffix="" step={0.1} update={updateField} />
        <NumberField label={t("risk.maxCorrelation")} value={policy.max_correlation} field="max_correlation" suffix="" step={0.05} update={updateField} />
        <NumberField label={t("risk.timeStop")} value={policy.time_stop_hours} field="time_stop_hours" suffix="h" step={12} update={updateField} />
        <NumberField label={t("risk.atrMultiplier")} value={policy.atr_stop_multiplier} field="atr_stop_multiplier" suffix="x" step={0.5} update={updateField} />
      </div>

      {/* Allowed Strategies */}
      <div className="mt-6">
        <label className="text-dark-400 text-xs mb-2 block">{t("risk.allowedStrategies")}</label>
        <div className="flex gap-2 flex-wrap">
          {STRATEGY_TYPES.map((st) => {
            const allowed: string[] = policy.allowed_strategies || [];
            const selected = allowed.includes(st.value) || allowed.length === 0;
            return (
              <button
                key={st.value}
                onClick={() => toggleStrategy(st.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  selected
                    ? "bg-opacity-20 border"
                    : "border border-dark-500 text-dark-400 opacity-50"
                }`}
                style={selected ? {
                  background: `${regimeColor(activeRegime)}20`,
                  borderColor: regimeColor(activeRegime),
                  color: regimeColor(activeRegime),
                } : {}}
              >
                {st.label}
              </button>
            );
          })}
        </div>
        {(policy.allowed_strategies || []).length === 0 && (
          <p className="text-dark-400 text-xs mt-1">
            <AlertTriangle size={12} className="inline mr-1" />
            {lang === "zh" ? "留空 = 允许所有策略类型" : "Empty = all strategy types allowed"}
          </p>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-3 mt-8">
        <button
          onClick={saveRegime}
          disabled={saving}
          className="px-6 py-2.5 rounded-lg text-sm font-medium flex items-center gap-2 transition-all"
          style={{ background: regimeColor(activeRegime), color: "#fff" }}
        >
          <Save size={16} /> {t("risk.save")}
        </button>
        <button
          onClick={resetAll}
          disabled={saving}
          className="px-6 py-2.5 rounded-lg text-sm font-medium flex items-center gap-2 border border-dark-500 text-dark-400 hover:text-white transition-all"
        >
          <RotateCcw size={16} /> {t("risk.reset")}
        </button>
      </div>
    </div>
  );
}

function NumberField({
  label, value, field, suffix, step, update,
}: {
  label: string; value: number; field: string; suffix: string; step: number;
  update: (f: string, v: number) => void;
}) {
  return (
    <div className="card">
      <label className="text-dark-400 text-xs block mb-1.5">{label}</label>
      <div className="flex items-center gap-1">
        <input
          type="number"
          value={value ?? 0}
          step={step}
          min={0}
          max={suffix === "%" ? 100 : (suffix === "h" ? 999 : 10)}
          onChange={(e) => update(field, parseFloat(e.target.value) || 0)}
          className="bg-dark-600 border border-dark-500 rounded-lg px-3 py-1.5 text-sm w-24 focus:outline-none focus:border-[#f0b90b]"
        />
        <span className="text-dark-400 text-xs">{suffix}</span>
      </div>
    </div>
  );
}
