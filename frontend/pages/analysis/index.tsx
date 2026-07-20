import { useState, useEffect } from "react";
import { api } from "../../lib/api";
import { useLanguage } from "../../lib/LanguageContext";
import { Brain, Activity, BarChart3, TrendingUp, TrendingDown, RefreshCw, ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";

export default function AnalysisPage() {
  const [indicators, setIndicators] = useState<Record<string, any> | null>(null);
  const [prediction, setPrediction] = useState<Record<string, any> | null>(null);
  const [regime, setRegime] = useState<Record<string, any> | null>(null);
  const [training, setTraining] = useState(false);
  const [trainResult, setTrainResult] = useState<Record<string, any> | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const { t } = useLanguage();

  useEffect(() => {
    api.getIndicators().then(setIndicators).catch(() => {});
    api.getPrediction().then(setPrediction).catch(() => {});
    api.getMarketRegime().then(setRegime).catch(() => {});
  }, [refreshKey]);

  const trainModel = async () => {
    setTraining(true);
    try {
      const result = await api.trainModel("BTC/USDT", "1h", 1000);
      setTrainResult(result);
      setRefreshKey((k) => k + 1);
    } catch (e) { setTrainResult({ error: String(e) }); }
    setTraining(false);
  };

  const SignalBadge = ({ signal }: { signal: string }) => {
    if (signal === "buy") return <span className="flex items-center gap-1 text-green"><ArrowUpRight size={14} /> BUY</span>;
    if (signal === "sell") return <span className="flex items-center gap-1 text-red"><ArrowDownRight size={14} /> SELL</span>;
    return <span className="flex items-center gap-1 text-dark-400"><Minus size={14} /> HOLD</span>;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">{t("analysis.title")}</h2>
          <p className="text-xs text-dark-400 mt-1">{t("analysis.subtitle")}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={trainModel} disabled={training} className="btn-primary flex items-center gap-2 text-sm">
            <Brain size={16} /> {training ? t("analysis.training") : t("analysis.train")}
          </button>
          <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost text-sm"><RefreshCw size={14} /></button>
        </div>
      </div>

      {trainResult && (
        <div className="card border-purple-500/20">
          <h3 className="text-sm font-semibold text-white mb-3">{t("analysis.result")}</h3>
          {trainResult.error ? <p className="text-red text-xs">{trainResult.error}</p> : (
            <div className="grid grid-cols-5 gap-4 text-xs">
              <div><span className="text-dark-400">{t("analysis.samples")}</span><p className="font-mono text-dark-200 mt-1">{trainResult.train_samples} train / {trainResult.test_samples} test</p></div>
              <div><span className="text-dark-400">{t("analysis.trainAcc")}</span><p className="font-mono text-green mt-1">{(trainResult.train_accuracy * 100).toFixed(1)}%</p></div>
              <div><span className="text-dark-400">{t("analysis.testAcc")}</span><p className={`font-mono mt-1 ${(trainResult.test_accuracy || 0) > 0.5 ? "text-green" : "text-red"}`}>{(trainResult.test_accuracy * 100).toFixed(1)}%</p></div>
              <div><span className="text-dark-400">{t("analysis.features")}</span><p className="font-mono text-dark-200 mt-1">{trainResult.feature_count}</p></div>
              <div><span className="text-dark-400">{t("analysis.model")}</span><p className="font-mono text-dark-200 mt-1">GradientBoosting</p></div>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card">
          <div className="flex items-center gap-2 mb-4"><Activity size={16} className="text-okx-yellow" /><h3 className="text-sm font-semibold text-white">{t("analysis.regime")}</h3></div>
          {regime ? (
            <div className="space-y-4">
              <div className="flex items-center justify-center">
                <div className={`text-2xl font-bold ${regime.regime === "bull" ? "text-green" : regime.regime === "bear" ? "text-red" : "text-okx-yellow"}`}>
                  {t(`enum.${regime.regime}`).toUpperCase()}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="card py-2"><span className="text-dark-400 block">{t("dash.volatility")}</span><span className="font-semibold text-dark-200">{t(`enum.${regime.volatility}`).toUpperCase()}</span></div>
                <div className="card py-2"><span className="text-dark-400 block">{t("dash.rsi")}</span><span className={`font-semibold font-mono ${(regime.rsi || 0) > 70 ? "text-red" : (regime.rsi || 0) < 30 ? "text-green" : "text-dark-200"}`}>{regime.rsi?.toFixed(1)}</span></div>
                <div className="card py-2"><span className="text-dark-400 block">{t("dash.vsSma20")}</span><span className={`font-semibold font-mono ${(regime.price_vs_sma20 || 0) >= 0 ? "text-green" : "text-red"}`}>{regime.price_vs_sma20?.toFixed(2)}%</span></div>
                <div className="card py-2"><span className="text-dark-400 block">{t("dash.vsSma50")}</span><span className={`font-semibold font-mono ${(regime.price_vs_sma50 || 0) >= 0 ? "text-green" : "text-red"}`}>{regime.price_vs_sma50?.toFixed(2)}%</span></div>
              </div>
            </div>
          ) : <div className="py-8 text-center text-dark-500 text-xs">{t("analysis.loading")}</div>}
        </div>

        <div className="card">
          <div className="flex items-center gap-2 mb-4"><Brain size={16} className="text-purple-400" /><h3 className="text-sm font-semibold text-white">{t("analysis.predict")}</h3></div>
          {prediction ? (
            <div className="space-y-4">
              <div className="flex items-center justify-center flex-col py-4">
                <SignalBadge signal={prediction.signal} />
                <div className="text-2xl font-bold font-mono mt-2 text-white">${prediction.current_price?.toFixed(2)}</div>
                <span className="text-xs text-dark-400 mt-1">{t("analysis.up")}: {prediction.prediction === "up" ? t("analysis.up") : t("analysis.down")}</span>
              </div>
              <div className="space-y-2 text-xs">
                <div><div className="flex justify-between mb-1"><span className="text-green">{t("analysis.upProb")}</span><span className="text-green font-mono">{(prediction.prob_up * 100).toFixed(1)}%</span></div>
                  <div className="w-full bg-dark-800 rounded-full h-2"><div className="h-2 rounded-full bg-okx-green" style={{ width: `${(prediction.prob_up * 100).toFixed(0)}%` }} /></div></div>
                <div><div className="flex justify-between mb-1"><span className="text-red">{t("analysis.downProb")}</span><span className="text-red font-mono">{(prediction.prob_down * 100).toFixed(1)}%</span></div>
                  <div className="w-full bg-dark-800 rounded-full h-2"><div className="h-2 rounded-full bg-okx-red" style={{ width: `${(prediction.prob_down * 100).toFixed(0)}%` }} /></div></div>
              </div>
              <div className="text-xs text-dark-400 text-center">{t("analysis.confidence")}: {(prediction.confidence * 100).toFixed(1)}%</div>
            </div>
          ) : (
            <div className="py-8 text-center text-dark-500 text-xs">
              <Brain size={32} className="mx-auto mb-2 opacity-30" />{t("analysis.trainHint")}
            </div>
          )}
        </div>

        <div className="card">
          <div className="flex items-center gap-2 mb-4"><BarChart3 size={16} className="text-okx-blue" /><h3 className="text-sm font-semibold text-white">{t("analysis.tech")}</h3></div>
          {indicators ? (
            <div className="space-y-3 text-xs">
              {[{ label: "RSI (14)", value: indicators.rsi, color: (indicators.rsi || 0) > 70 ? "text-red" : (indicators.rsi || 0) < 30 ? "text-green" : "text-dark-200" },
                { label: "MACD", value: indicators.macd, color: (indicators.macd || 0) >= 0 ? "text-green" : "text-red" },
                { label: "MACD Signal", value: indicators.macd_signal, color: "text-dark-200" },
                { label: "BB Upper", value: indicators.bb_upper?.toFixed(0), color: "text-dark-200" },
                { label: "BB Lower", value: indicators.bb_lower?.toFixed(0), color: "text-dark-200" },
                { label: "BB Width", value: indicators.bb_width, color: "text-dark-200" },
                { label: "EMA 9", value: indicators.ema_9?.toFixed(0), color: "text-okx-blue" },
                { label: "EMA 21", value: indicators.ema_21?.toFixed(0), color: "text-okx-yellow" },
                { label: "EMA 50", value: indicators.ema_50?.toFixed(0), color: "text-dark-400" },
                { label: "ATR (14)", value: indicators.atr?.toFixed(2), color: "text-dark-200" },
                { label: "Volume Ratio", value: indicators.volume_ratio?.toFixed(2), color: (indicators.volume_ratio || 0) > 1.5 ? "text-green" : "text-dark-200" },
              ].map((item) => (
                <div key={item.label} className="flex justify-between py-1 border-b border-dark-800/50 last:border-0">
                  <span className="text-dark-400">{item.label}</span>
                  <span className={`font-mono ${item.color}`}>{item.value}</span>
                </div>
              ))}
            </div>
          ) : <div className="py-8 text-center text-dark-500 text-xs">{t("dash.loading")}</div>}
        </div>
      </div>
    </div>
  );
}
