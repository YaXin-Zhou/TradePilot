import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import { Brain, Send, Zap, RefreshCw, TrendingUp, TrendingDown, Minus, ArrowUpRight, ArrowDownRight } from "lucide-react";
import type { AiAnalyzeResult, AiAnalyzeRequest } from "../types/strategy";
import type { Ticker, Balance, PlaceOrderResult } from "../types/portfolio";
import type { ApiError } from "../types/api";
import { asApiError } from "../types/api";


export default function AIStrategyPage() {
  const [strategy, setStrategy] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiAnalyzeResult | null>(null);
  const [ticker, setTicker] = useState<Ticker | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [orderAmount, setOrderAmount] = useState(100);
  const [placingOrder, setPlacingOrder] = useState(false);
  const [placedOrder, setPlacedOrder] = useState<PlaceOrderResult | null>(null);

  useEffect(() => {
    api.getTicker().then(setTicker).catch(() => {});
    api.getBalance().then(setBalance).catch(() => {});
    api.testAIConnection().then(() => setConnected(true)).catch(() => setConnected(false));
  }, []);

  const analyze = async () => {
    if (!strategy.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const req: AiAnalyzeRequest = { strategy_desc: strategy, auto: false };
      const res = await api.aiAnalyze(req);
      setResult(res);
    } catch (e: unknown) {
      setResult({ error: asApiError(e).message });
    }
    setLoading(false);
  };

  const placeOrder = async (signal: string) => {
    const side = signal.includes("buy") ? "buy" : "sell";
    setPlacingOrder(true);
    setPlacedOrder(null);
    try {
      const res = await api.placeMarketOrder({ side, amount: orderAmount });
      setPlacedOrder(res);
    } catch (e: unknown) {
      setPlacedOrder({ id: "", symbol: "", side: "buy", amount: 0, status: "error", timestamp: 0, error: asApiError(e).message });
    }
    setPlacingOrder(false);
  };

  const autoAnalyze = async () => {
    setLoading(true);
    setResult(null);
    try {
      const req: AiAnalyzeRequest = { strategy_desc: "", auto: true };
      const res = await api.aiAnalyze(req);
      setResult(res);
    } catch (e: unknown) {
      setResult({ error: asApiError(e).message });
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
      <div><h2 className="text-lg font-semibold text-white">AI Strategy</h2><p className="text-xs text-dark-400 mt-1">AI generates strategies with automatic backtesting</p></div>

      {/* AI 连接状态指示 */}
      <div className="card py-2 px-4 flex items-center gap-2">
        <Zap size={14} className={connected === true ? "text-green" : connected === false ? "text-red" : "text-dark-500"} />
        <span className="text-xs text-dark-300">
          {connected === true ? "DeepSeek API 已连接" : connected === false ? "DeepSeek API 未配置，请在 .env 设置 DEEPSEEK_API_KEY" : "检测 DeepSeek 连接..."}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="card">
            <div className="flex items-center gap-2 mb-3"><Brain size={16} className="text-indigo-400" /><span className="text-sm font-semibold text-white">Strategy Description</span></div>
            <textarea value={strategy} onChange={(e) => setStrategy(e.target.value)}
              placeholder="Buy when RSI(14) < 30 and price above EMA200&#10;Sell when RSI(14) > 70&#10;Position size: 10%&#10;Stop loss: 2%"
              className="w-full h-32 resize-none text-sm" style={{fontFamily:"monospace"}} />
            <button onClick={analyze} disabled={loading || !strategy.trim()}
              className="btn-primary flex items-center gap-2 text-sm mt-3 w-full justify-center">
              {loading ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
              {loading ? "Analyzing and Backtesting..." : "Analyze and Backtest"}
            </button>
            <button onClick={autoAnalyze} disabled={loading} className="btn-ghost w-full flex items-center justify-center gap-2 text-sm py-2.5 mt-2">
              <Zap size={14} /> Auto Analyze
            </button>
          </div>

          {ticker && (
            <div className="card">
              <span className="text-sm font-semibold text-white mb-3 block">Current Market</span>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><span className="text-dark-400">Price</span><p className="font-mono text-white">${ticker.last?.toFixed(2)}</p></div>
                <div><span className="text-dark-400">24h</span><p className={"font-mono " + ((ticker.change_pct ?? 0) >= 0 ? "text-green" : "text-red")}>{ticker.change_pct?.toFixed(2)}%</p></div>
                <div><span className="text-dark-400">High/Low</span><p className="font-mono text-dark-200">${ticker.high?.toFixed(0)} / ${ticker.low?.toFixed(0)}</p></div>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          {loading && (
            <div className="card flex items-center justify-center py-12">
              <div className="text-center"><Brain size={40} className="mx-auto mb-3 text-purple-400 animate-pulse" /><p className="text-sm text-dark-400">AI is analyzing...</p></div>
            </div>
          )}

          {result && !loading && (
            <div className="card border-indigo-500/20">
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm font-semibold text-white">AI Signal</span>
                {result.signal && <SignalBadge signal={result.signal} />}
              </div>
              {result.confidence != null && (
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
                    {Object.entries(result.indicators).map(([k, v]: [string, number | string]) => (
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
          {result && result.signal && (result.signal === "buy" || result.signal === "strong_buy" || result.signal === "sell" || result.signal === "strong_sell") && (
            <div className="mt-4 pt-4 border-t border-dark-800">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold text-white">Execute Trade</span>
                {balance && (
                  <span className="text-xs text-dark-400">
                    USDT: ${balance.USDT?.free?.toFixed(2) || "0.00"}
                  </span>
                )}
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-xs text-dark-400 block mb-1">Amount (USDT)</label>
                  <input type="number" value={orderAmount}
                    onChange={e => setOrderAmount(Number(e.target.value))}
                    className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
                </div>
                <button onClick={() => placeOrder(result.signal || "")}
                  disabled={placingOrder}
                  className="w-full flex items-center justify-center gap-2 text-sm py-2.5 rounded font-semibold"
                  style={{
                    background: result.signal.includes("buy") ? "#00c076" : "#f6465d",
                    color: "#000",
                    opacity: placingOrder ? 0.6 : 1,
                  }}>
                  {placingOrder ? "Placing..." : result.signal.includes("buy") ? "Buy BTC" : "Sell BTC"}
                </button>
                {placedOrder && (
                  <div className={`text-xs p-2 rounded ${placedOrder.error ? "bg-okx-red/10 text-okx-red" : "bg-okx-green/10 text-okx-green"}`}>
                    {placedOrder.error
                      ? "Error: " + placedOrder.error
                      : "Order placed! ID: " + placedOrder.id + " Status: " + placedOrder.status}
                  </div>
                )}
                {result.strategy_description && (
                  <div className="mt-3 pt-3 border-t border-dark-800">
                    <span className="text-xs font-semibold text-white mb-2 block">AI Generated Strategy</span>
                    <p className="text-xs text-dark-300">{result.strategy_description}</p>
                    {result.market_assessment && <p className="text-xs text-dark-500 mt-1">Market: {result.market_assessment}</p>}
                  </div>
                )}
                {result.backtest && (
                  <div className="mt-3 pt-3 border-t border-dark-800">
                    <span className="text-xs font-semibold text-white mb-2 block">Backtest Result</span>
                    <div className="grid grid-cols-2 gap-1 text-xs">
                      <div className="flex justify-between py-0.5"><span className="text-dark-400">Return</span><span className={"font-mono " + ((result.backtest.total_return_pct ?? 0) >= 0 ? "text-okx-green" : "text-okx-red")}>{result.backtest.total_return_pct?.toFixed(2)}%</span></div>
                      <div className="flex justify-between py-0.5"><span className="text-dark-400">Sharpe</span><span className="font-mono text-dark-200">{result.backtest.sharpe_ratio?.toFixed(2)}</span></div>
                      <div className="flex justify-between py-0.5"><span className="text-dark-400">Max DD</span><span className="font-mono text-okx-red">{result.backtest.max_drawdown_pct?.toFixed(2)}%</span></div>
                      <div className="flex justify-between py-0.5"><span className="text-dark-400">Win Rate</span><span className="font-mono text-okx-blue">{result.backtest.win_rate?.toFixed(0)}%</span></div>
                      <div className="flex justify-between py-0.5"><span className="text-dark-400">Trades</span><span className="font-mono text-dark-200">{result.backtest.total_trades}</span></div>
                      <div className="flex justify-between py-0.5"><span className="text-dark-400">Profit Factor</span><span className="font-mono text-okx-green">{result.backtest.profit_factor?.toFixed(2)}</span></div>
                    </div>
                    <div className="mt-2 text-xs text-dark-500">Strategy: {result.strategy_type} | Params: {JSON.stringify(result.strategy_params)}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {!result && !loading && (
            <div className="card flex items-center justify-center py-16">
              <div className="text-center"><Brain size={48} className="mx-auto mb-3 text-dark-600" /><p className="text-sm text-dark-400">Describe your strategy and click Analyze</p></div>
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
