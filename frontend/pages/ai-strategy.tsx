import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import { BrainCircuit, Send, Zap, Key, RefreshCw, TrendingUp, TrendingDown, Minus, ArrowUpRight, ArrowDownRight } from "lucide-react";

export default function AIStrategyPage() {
  const [apiKey, setApiKey] = useState("");
  const [strategy, setStrategy] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [ticker, setTicker] = useState<any>(null);
  const [connected, setConnected] = useState(false);
  const [keySaved, setKeySaved] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("deepseek_key");
    if (saved) setApiKey(saved);
    api.getTicker().then(setTicker).catch(() => {});
  }, []);

  const saveKey = () => {
    localStorage.setItem("deepseek_key", apiKey);
    setKeySaved(true);
    setTimeout(() => setKeySaved(false), 2000);
  };

  const testConnection = async () => {
    if (!apiKey) return;
    try {
      await api.testAIConnection(apiKey);
      setConnected(true);
    } catch (e: any) {
      setConnected(false);
    }
  };

  const analyze = async () => {
    if (!apiKey || !strategy.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await api.aiAnalyze({ api_key: apiKey, strategy_desc: strategy });
      setResult(res);
    } catch (e: any) {
      setResult({ error: e.message });
    }
    setLoading(false);
  };

  const SignalBadge = ({ signal }: { signal: string }) => {
    if (signal === "buy" || signal === "strong_buy")
      return <span className="text-green text-lg font-bold flex items-center gap-1"><ArrowUpRight size={20} />{signal === "strong_buy" ? "STRONG BUY" : "BUY"}</span>;
    if (signal === "sell" || signal === "strong_sell")
      return <span className="text-red text-lg font-bold flex items-center gap-1"><ArrowDownRight size={20} />{signal === "strong_sell" ? "STRONG SELL" : "SELL"}</span>;
    return <span className="text-dark-400 text-lg flex items-center gap-1"><Minus size={20} />HOLD</span>;
  };

  return (
    <div className="space-y-6">
      <div><h2 className="text-lg font-semibold text-white">AI Strategy</h2><p className="text-xs text-dark-400 mt-1">Natural language trading strategy with DeepSeek AI</p></div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="card">
            <div className="flex items-center gap-2 mb-3"><Key size={16} className="text-purple-400" /><span className="text-sm font-semibold text-white">DeepSeek API Key</span></div>
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." className="w-full" />
            <div className="flex gap-2 mt-2">
              <button onClick={saveKey} className="btn-ghost text-xs py-1.5">{keySaved ? "Saved!" : "Save Key"}</button>
              <button onClick={testConnection} className="btn-ghost text-xs py-1.5 flex items-center gap-1"><Zap size={12} /> Test</button>
              {connected && <span className="text-xs text-green flex items-center">Connected</span>}
            </div>
          </div>

          <div className="card">
            <div className="flex items-center gap-2 mb-3"><BrainCircuit size={16} className="text-indigo-400" /><span className="text-sm font-semibold text-white">Strategy Description</span></div>
            <textarea value={strategy} onChange={(e) => setStrategy(e.target.value)}
              placeholder="Buy when RSI(14) < 30 and price above EMA200&#10;Sell when RSI(14) > 70&#10;Position size: 10%&#10;Stop loss: 2%"
              className="w-full h-32 resize-none text-sm" style={{fontFamily:"monospace"}} />
            <button onClick={analyze} disabled={loading || !apiKey || !strategy.trim()}
              className="btn-primary flex items-center gap-2 text-sm mt-3 w-full justify-center">
              {loading ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
              {loading ? "Analyzing..." : "Analyze Market"}
            </button>
          </div>

          {ticker && (
            <div className="card">
              <span className="text-sm font-semibold text-white mb-3 block">Current Market</span>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><span className="text-dark-400">Price</span><p className="font-mono text-white">${ticker.last?.toFixed(2)}</p></div>
                <div><span className="text-dark-400">24h</span><p className={"font-mono " + (ticker.change_pct >= 0 ? "text-green" : "text-red")}>{ticker.change_pct?.toFixed(2)}%</p></div>
                <div><span className="text-dark-400">High/Low</span><p className="font-mono text-dark-200">${ticker.high?.toFixed(0)} / ${ticker.low?.toFixed(0)}</p></div>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          {loading && (
            <div className="card flex items-center justify-center py-12">
              <div className="text-center"><BrainCircuit size={40} className="mx-auto mb-3 text-purple-400 animate-pulse" /><p className="text-sm text-dark-400">AI is analyzing...</p></div>
            </div>
          )}

          {result && !loading && (
            <div className="card border-indigo-500/20">
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm font-semibold text-white">AI Signal</span>
                <SignalBadge signal={result.signal} />
              </div>
              {result.confidence && (
                <div className="mb-3">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-dark-400">Confidence</span>
                    <span className="font-mono text-dark-200">{(result.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="w-full bg-dark-800 rounded-full h-2">
                    <div className="h-2 rounded-full bg-indigo-500" style={{width: (result.confidence * 100).toFixed(0) + "%"}} />
                  </div>
                </div>
              )}
              <div className="text-xs space-y-2">
                <div><span className="text-dark-400">Price</span><p className="font-mono text-dark-200">${result.current_price?.toFixed(2)}</p></div>
                <div><span className="text-dark-400">Reasoning</span><p className="text-dark-200 mt-1">{result.reason || "N/A"}</p></div>
              </div>
              {result.indicators && (
                <div className="mt-3 pt-3 border-t border-dark-800">
                  <span className="text-xs font-semibold text-white mb-2 block">Indicators</span>
                  <div className="grid grid-cols-2 gap-1 text-xs">
                    {Object.entries(result.indicators).map(([k, v]: [string, any]) => (
                      <div key={k} className="flex justify-between py-0.5">
                        <span className="text-dark-400">{k.toUpperCase()}</span>
                        <span className="font-mono text-dark-200">{typeof v === "number" ? v.toFixed(2) : String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!result && !loading && (
            <div className="card flex items-center justify-center py-16">
              <div className="text-center"><BrainCircuit size={48} className="mx-auto mb-3 text-dark-600" /><p className="text-sm text-dark-400">Describe your strategy and click Analyze</p></div>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <span className="text-sm font-semibold text-white mb-3 block">Strategy Examples</span>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          {[
            {title:"RSI Mean Reversion", desc:"Buy when RSI(14) < 30, sell when > 70. Use 50 SMA as trend filter."},
            {title:"MACD Crossover", desc:"Buy when MACD crosses above signal line. Sell when crosses below."},
            {title:"Bollinger Squeeze", desc:"Buy when price touches lower band and RSI < 30. Sell at upper band."},
          ].map((ex) => (
            <div key={ex.title} className="card py-3 cursor-pointer hover:border-indigo-500/30" onClick={() => setStrategy(ex.desc)}>
              <p className="font-semibold text-dark-200 mb-1">{ex.title}</p>
              <p className="text-dark-400">{ex.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
