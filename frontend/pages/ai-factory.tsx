import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { Brain, Zap, RefreshCw, TrendingUp, BarChart3, Target, Shield, Activity, Sparkles } from "lucide-react";
import type { AiAnalyzeResult, AiAnalyzeRequest } from "../types/strategy";
import type { ApiError } from "../types/api";
import { asApiError } from "../types/api";

const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
const TIMEFRAMES = ["15m", "1h", "4h", "1d"];

export default function AIFactoryPage() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AiAnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aiConnected, setAiConnected] = useState<boolean | null>(null);
  const [history, setHistory] = useState<AiAnalyzeResult[]>([]);

  useEffect(() => {
    api.testAIConnection().then(() => setAiConnected(true)).catch(() => setAiConnected(false));
  }, []);

  const runAnalysis = async () => {
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const req: AiAnalyzeRequest = { strategy_desc: "", auto: true, symbol, timeframe } as AiAnalyzeRequest & { symbol: string; timeframe: string };
      const res = await api.aiAnalyze(req);
      setResult(res);
      setHistory(prev => [res, ...prev].slice(0, 10));
    } catch (e: unknown) {
      setError(asApiError(e).message);
    }
    setLoading(false);
  };

  const formatPct = (v?: number) => (v != null ? (v >= 0 ? "+" : "") + v.toFixed(2) + "%" : "-");
  const pctColor = (v?: number) => (v != null ? (v >= 0 ? "text-green" : "text-red") : "text-dark-400");

  return (
    <div className="space-y-6">
      {/* 标题 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Sparkles size={20} className="text-indigo-400" />
            AI 策略工厂
          </h2>
          <p className="text-xs text-dark-400 mt-1">不懂金融也没关系 — AI 自动分析市场、生成策略、回测验证，一键搞定</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${aiConnected === true ? "bg-green" : aiConnected === false ? "bg-red" : "bg-dark-500"}`} />
          <span className="text-xs text-dark-400">
            {aiConnected === true ? "DeepSeek 已连接" : aiConnected === false ? "AI 未连接" : "检测中..."}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 左侧：控制面板 */}
        <div className="lg:col-span-1 space-y-4">
          {/* 参数选择 */}
          <div className="card">
            <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <Target size={14} className="text-indigo-400" /> 参数设置
            </h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-dark-400 block mb-1">交易对</label>
                <div className="flex gap-1">
                  {SYMBOLS.map(s => (
                    <button
                      key={s}
                      onClick={() => setSymbol(s)}
                      className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                        symbol === s ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30" : "bg-dark-800 text-dark-300 border border-dark-700 hover:border-dark-600"
                      }`}
                    >
                      {s.split("/")[0]}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs text-dark-400 block mb-1">K 线周期</label>
                <div className="flex gap-1">
                  {TIMEFRAMES.map(tf => (
                    <button
                      key={tf}
                      onClick={() => setTimeframe(tf)}
                      className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                        timeframe === tf ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30" : "bg-dark-800 text-dark-300 border border-dark-700 hover:border-dark-600"
                      }`}
                    >
                      {tf}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* 主按钮 */}
          <button
            onClick={runAnalysis}
            disabled={loading}
            className="w-full py-4 rounded-lg font-semibold text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50"
            style={{
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
              color: "#fff",
            }}
          >
            {loading ? (
              <>
                <RefreshCw size={18} className="animate-spin" />
                AI 分析中，请稍候...
              </>
            ) : (
              <>
                <Zap size={18} />
                AI 一键生成策略并回测
              </>
            )}
          </button>

          {/* 错误 */}
          {error && (
            <div className="card border-red-500/30 bg-red-500/5">
              <p className="text-xs text-red-400">{error}</p>
            </div>
          )}

          {/* 历史记录 */}
          {history.length > 0 && (
            <div className="card">
              <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                <Activity size={14} className="text-dark-400" /> 历史记录
              </h3>
              <div className="space-y-1">
                {history.map((h, i) => (
                  <button
                    key={i}
                    onClick={() => setResult(h)}
                    className="w-full text-left p-2 rounded bg-dark-800 hover:bg-dark-700 transition-colors text-xs"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-dark-300">{h.strategy_type || "AI 策略"}</span>
                      <span className={pctColor(h.backtest?.total_return_pct)}>
                        {formatPct(h.backtest?.total_return_pct)}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 右侧：结果展示 */}
        <div className="lg:col-span-2 space-y-4">
          {loading && (
            <div className="card flex flex-col items-center justify-center py-20">
              <Brain size={48} className="text-indigo-400 animate-pulse mb-4" />
              <p className="text-sm text-dark-400 mb-1">AI 正在分析 {symbol} 市场数据</p>
              <p className="text-xs text-dark-500">获取行情 → 计算指标 → DeepSeek 分析 → 生成策略 → 回测验证</p>
              <div className="flex gap-1 mt-4">
                {[1, 2, 3, 4, 5].map(i => (
                  <div key={i} className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          )}

          {!loading && !result && (
            <div className="card flex flex-col items-center justify-center py-20">
              <Brain size={48} className="text-dark-600 mb-4" />
              <p className="text-sm text-dark-400">点击左侧「AI 一键生成策略并回测」开始</p>
              <p className="text-xs text-dark-500 mt-1">AI 会分析当前市场，自动选择最优策略并回测</p>
            </div>
          )}

          {result && !loading && (
            <>
              {/* AI 策略卡片 */}
              {result.strategy_description && (
                <div className="card border-indigo-500/20">
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Brain size={16} className="text-indigo-400" /> AI 生成策略
                  </h3>
                  <p className="text-sm text-dark-200 leading-relaxed">{result.strategy_description}</p>
                  {result.market_assessment && (
                    <p className="text-xs text-dark-500 mt-2">市场评估：{result.market_assessment}</p>
                  )}
                  <div className="flex gap-2 mt-3">
                    <span className="px-2 py-0.5 rounded text-xs bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                      {result.strategy_type}
                    </span>
                    {result.signal && (
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        result.signal.includes("buy") ? "bg-green/10 text-green border border-green/20" :
                        result.signal.includes("sell") ? "bg-red/10 text-red border border-red/20" :
                        "bg-dark-800 text-dark-300 border border-dark-700"
                      }`}>
                        信号：{result.signal.toUpperCase()}
                      </span>
                    )}
                  </div>
                  {/* 自动入库提示 */}
                  {result.strategy_id && (
                    <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded bg-green/5 border border-green/10">
                      <span className="text-green text-xs">✅ 已自动保存到策略库</span>
                      <span className="text-dark-500 text-xs">ID: {result.strategy_id.slice(0, 8)}...</span>
                      {result.pool_registered && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400">策略池</span>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* 回测结果 */}
              {result.backtest ? (
                <div className="card border-green-500/10">
                  <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <BarChart3 size={16} className="text-green" /> 回测结果
                  </h3>
                  <div className="grid grid-cols-3 gap-4">
                    <MetricCard icon={TrendingUp} label="收益率" value={formatPct(result.backtest.total_return_pct)} color={pctColor(result.backtest.total_return_pct)} />
                    <MetricCard icon={Shield} label="夏普比率" value={(result.backtest.sharpe_ratio ?? 0).toFixed(2)} color="text-indigo-400" />
                    <MetricCard icon={Target} label="最大回撤" value={formatPct(result.backtest.max_drawdown_pct)} color="text-red" />
                    <MetricCard icon={Activity} label="胜率" value={(result.backtest.win_rate ?? 0).toFixed(0) + "%"} color="text-blue-400" />
                    <MetricCard icon={BarChart3} label="交易次数" value={String(result.backtest.total_trades ?? 0)} color="text-dark-200" />
                    <MetricCard icon={TrendingUp} label="盈亏比" value={(result.backtest.profit_factor ?? 0).toFixed(2)} color={(result.backtest.profit_factor ?? 0) >= 1 ? "text-green" : "text-red"} />
                  </div>
                  <div className="mt-3 pt-3 border-t border-dark-800 text-xs text-dark-500">
                    策略：{result.strategy_type} | 参数：{JSON.stringify(result.strategy_params)}
                  </div>
                </div>
              ) : result.error ? (
                <div className="card border-red-500/30 bg-red-500/5">
                  <p className="text-sm text-red-400">{result.error}</p>
                </div>
              ) : null}

              {/* 技术指标 */}
              {result.indicators && (
                <div className="card">
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Activity size={16} className="text-dark-400" /> 技术指标快照
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    {Object.entries(result.indicators).slice(0, 12).map(([k, v]) => (
                      <div key={k} className="flex justify-between py-1 px-2 rounded bg-dark-800">
                        <span className="text-dark-400">{k.toUpperCase()}</span>
                        <span className="font-mono text-dark-200 ml-2">{typeof v === "number" ? v.toFixed(2) : String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, color }: {
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="p-3 rounded bg-dark-800 border border-dark-700">
      <div className="flex items-center gap-1.5 mb-1">
        <Icon size={12} className={color} />
        <span className="text-xs text-dark-400">{label}</span>
      </div>
      <p className={`text-lg font-bold font-mono ${color}`}>{value}</p>
    </div>
  );
}
