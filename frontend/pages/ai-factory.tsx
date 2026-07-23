import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../lib/api";
import { Brain, Zap, RefreshCw, TrendingUp, BarChart3, Target, Shield, Activity, Sparkles, CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import type { AiAnalyzeResult, AiAnalyzeRequest } from "../types/strategy";
import type { ApiError } from "../types/api";
import { asApiError } from "../types/api";
import type { IterationTaskDetail, IterationVariant } from "../types/ai-lab";

const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
const TIMEFRAMES = ["15m", "1h", "4h", "1d"];

export default function AIFactoryPage() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiConnected, setAiConnected] = useState<boolean | null>(null);
  const [history, setHistory] = useState<AiAnalyzeResult[]>(() => {
    if (typeof window !== "undefined") {
      try { const s = localStorage.getItem("ai_results"); return s ? JSON.parse(s) : []; } catch { return []; }
    }
    return [];
  });
  const [result, setResult] = useState<AiAnalyzeResult | null>(() => {
    if (typeof window !== "undefined") {
      try { const s = localStorage.getItem("ai_results"); const arr = s ? JSON.parse(s) : []; return arr[0] || null; } catch { return null; }
    }
    return null;
  });

  // 保存结果到 localStorage
  const saveHistory = (items: AiAnalyzeResult[]) => {
    setHistory(items);
    try { localStorage.setItem("ai_results", JSON.stringify(items.slice(0, 10))); } catch {}
  };

  // 迭代优化状态
  const [iterating, setIterating] = useState(false);
  const [iterTaskId, setIterTaskId] = useState<string | null>(null);
  const [iterProgress, setIterProgress] = useState<Record<string, any> | null>(null);
  const [iterBest, setIterBest] = useState<Record<string, any> | null>(null);
  const [iterError, setIterError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const iterTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 保存迭代结果到策略库
  const saveToWarehouse = async () => {
    if (!iterBest || !result) return;
    setSaving(true);
    try {
      const res: any = await api.saveIterationToWarehouse({
        strategy_type: iterBest.strategy_type,
        params: iterBest.params,
        symbol,
        metrics: {
          sharpe_oos: iterBest.sharpe_oos,
          max_drawdown_pct: iterBest.max_drawdown_pct,
          win_rate: iterBest.win_rate,
          total_trades: iterBest.total_trades,
          total_return_pct: iterBest.total_return_pct,
        },
      });
      if (res?.strategy_id) {
        setIterError(null);
        alert(`策略已保存到策略库: ${res.name}`);
      } else {
        setIterError("保存失败: " + (res?.error || "未知错误"));
      }
    } catch {
      setIterError("保存到策略库失败");
    }
    setSaving(false);
  };

  useEffect(() => {
    api.testAIConnection().then(() => setAiConnected(true)).catch(() => setAiConnected(false));
  }, []);

  const runAnalysis = async () => {
    setLoading(true);
    setResult(null);
    setError(null);
    // 清除旧迭代残留
    setIterating(false); setIterProgress(null); setIterBest(null); setIterError(null);
    try {
      const req: AiAnalyzeRequest = { strategy_desc: "", auto: true, symbol, timeframe } as AiAnalyzeRequest & { symbol: string; timeframe: string };
      const res = await api.aiAnalyze(req);
      setResult(res);
      saveHistory([res, ...history].slice(0, 10));
    } catch (e: unknown) {
      setError(asApiError(e).message);
    }
    setLoading(false);
  };

  const formatPct = (v?: number) => (v != null ? (v >= 0 ? "+" : "") + v.toFixed(2) + "%" : "-");
  const pctColor = (v?: number) => (v != null ? (v >= 0 ? "text-green" : "text-red") : "text-dark-400");

  // 启动迭代优化
  const startIteration = useCallback(async () => {
    if (!result?.strategy_type) return;
    setIterating(true);
    setIterError(null);
    setIterBest(null);
    try {
      const goal = `Optimize ${result.strategy_type} strategy for ${symbol} ${timeframe}. ` +
        `Current sharpe=${(result.backtest?.sharpe_ratio ?? 0).toFixed(2)}, ` +
        `drawdown=${(result.backtest?.max_drawdown_pct ?? 0).toFixed(1)}%. ` +
        `Goal: improve OOS sharpe and reduce overfitting (PBO≤0.5).`;
      const res: { task_id?: string; error?: string } = await api.startIteration({
        goal,
        symbol,
        timeframe,
        variants: 8,
        max_rounds: 5,
        risk_constraints: {
          max_drawdown_pct: Math.abs(result.backtest?.max_drawdown_pct ?? 20) * 1.2,
          min_sharpe: Math.max((result.backtest?.sharpe_ratio ?? 1) * 0.8, 0.5),
          max_concentration: 0.3,
        },
      });
      if (res?.task_id) {
        const tid = res.task_id;
        setIterTaskId(tid);
        pollIteration(tid);
      } else {
        setIterError("启动迭代失败: " + (res?.error || "未知错误"));
        setIterating(false);
      }
    } catch (e: unknown) {
      setIterError((e as { message?: string })?.message || "启动迭代失败");
      setIterating(false);
    }
  }, [result, symbol, timeframe]);

  // 轮询迭代进度（request() 已解包 json.data，直接就是状态对象）
  const pollIteration = useCallback((taskId: string) => {
    const poll = async () => {
      try {
        const s: any = await api.getIterationStatus(taskId);
        // s 是解包后的 data 对象：{task_id, status, current_round, ...}
        if (!s || !s.task_id) return;
        
        setIterProgress(s);
        if (s.status === "completed" || s.status === "converged") {
          const b: any = await api.getIterationBest(taskId);
          if (b) {
            setIterBest(b);
            setIterating(false);
            if (iterTimerRef.current) { clearInterval(iterTimerRef.current); iterTimerRef.current = null; }
            return;
          }
        }
        if (s.status === "failed") {
          setIterError(s.error || "迭代失败");
          setIterating(false);
          if (iterTimerRef.current) { clearInterval(iterTimerRef.current); iterTimerRef.current = null; }
          return;
        }
      } catch {}
    };
    poll();
    if (iterTimerRef.current) clearInterval(iterTimerRef.current);
    iterTimerRef.current = setInterval(poll, 4000);
  }, []);

  // 清理定时器
  useEffect(() => {
    return () => { if (iterTimerRef.current) clearInterval(iterTimerRef.current); };
  }, []);

  // 合格标准检测
  const isQualified = (v: Record<string, any> | null) => {
    if (!v) return false;
    return (v.sharpe_oos ?? 0) >= 1.0 && (v.pbo ?? 1) <= 0.3 && (v.max_drawdown_pct ?? 100) <= 15;
  };

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

                  {/* 过拟合验证结果 */}
                  {result.validation && (
                    <div className="mt-3 pt-3 border-t border-dark-700">
                      <div className="flex items-center gap-2 mb-2">
                        <Shield size={14} className={result.scientific_valid ? "text-green" : "text-red"} />
                        <span className={`text-xs font-medium ${result.scientific_valid ? "text-green" : "text-red"}`}>
                          {result.scientific_valid ? "✓ 科学验证通过（PBO≤0.5, OOS夏普>0）" : "✗ 未通过过拟合检测"}
                        </span>
                      </div>
                      <div className="grid grid-cols-4 gap-2">
                        <div className="text-xs text-dark-500">样本内夏普 <span className="text-dark-200 font-mono">{result.backtest?.sharpe_ratio?.toFixed(3) ?? "-"}</span></div>
                        <div className="text-xs text-dark-500">样本外夏普 <span className="text-dark-200 font-mono">{(result.validation?.sharpe_oos ?? 0).toFixed(3)}</span></div>
                        <div className="text-xs text-dark-500">PBO <span className={`font-mono ${(result.validation?.pbo ?? 1) <= 0.5 ? "text-green" : "text-yellow-400"}`}>{(result.validation?.pbo ?? 0).toFixed(3)}</span></div>
                        <div className="text-xs text-dark-500">DSR <span className="text-dark-200 font-mono">{(result.validation?.dsr ?? 0).toFixed(3)}</span></div>
                      </div>
                    </div>
                  )}

                  {result.auto_save_skipped && !iterating && !iterBest && (
                    <div className="mt-4 space-y-3">
                      <div className="px-3 py-2.5 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs text-yellow-400 flex items-center justify-between">
                        <span className="flex items-center gap-2">
                          <AlertTriangle size={13} />
                          策略未通过过拟合检测（PBO&gt;0.5 或 OOS夏普≤0），建议迭代优化
                        </span>
                        <button
                          onClick={startIteration}
                          className="px-3 py-1.5 rounded text-xs font-medium bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/30 transition-all flex items-center gap-1"
                        >
                          <Zap size={12} /> 启动迭代优化
                        </button>
                      </div>
                      <div className="text-xs text-dark-500 grid grid-cols-3 gap-2">
                        <div className="flex items-center gap-1"><Shield size={10} className="text-dark-600" /> 过拟合检测: PBO≤0.5</div>
                        <div className="flex items-center gap-1"><Shield size={10} className="text-dark-600" /> 数据泄漏防范: IS/OOS分离</div>
                        <div className="flex items-center gap-1"><Shield size={10} className="text-dark-600" /> 信号闪烁规避: OOS验证</div>
                      </div>
                    </div>
                  )}

                  {/* 迭代进度 */}
                  {iterating && iterProgress && (
                    <div className="mt-4 p-4 card border-indigo-500/30 bg-indigo-500/5">
                      <div className="flex items-center gap-2 mb-3">
                        <RefreshCw size={14} className="animate-spin text-indigo-400" />
                        <span className="text-sm font-medium text-indigo-400">迭代优化中...</span>
                        <span className="text-xs text-dark-400 ml-auto">
                          第 {iterProgress.current_round ?? 0}/{iterProgress.max_rounds ?? 5} 轮
                        </span>
                      </div>
                      <div className="h-1.5 bg-dark-700 rounded-full overflow-hidden mb-3">
                        <div className="h-full bg-indigo-500 transition-all duration-500 rounded-full"
                          style={{ width: `${((iterProgress.current_round ?? 0) / (iterProgress.max_rounds || 1)) * 100}%` }} />
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-xs text-dark-400">
                        <span>变体: {iterProgress.total_variants ?? 0}</span>
                        <span>科学通过: <span className="text-green">{iterProgress.scientific_passed ?? 0}</span></span>
                        <span>状态: {iterProgress.status ?? "running"}</span>
                      </div>
                    </div>
                  )}

                  {/* 迭代结果 */}
                  {iterBest && (
                    <div className="mt-4 p-4 card border-green-500/30 bg-green-500/5">
                      <div className="flex items-center gap-2 mb-3">
                        {isQualified(iterBest) ? (
                          <CheckCircle size={16} className="text-green" />
                        ) : (
                          <AlertTriangle size={16} className="text-yellow-400" />
                        )}
                        <span className={`text-sm font-medium ${isQualified(iterBest) ? "text-green" : "text-yellow-400"}`}>
                          {isQualified(iterBest) ? "✓ 迭代完成 — 策略达标！" : "迭代完成 — 策略已优化"}
                        </span>
                      </div>
                      <div className="grid grid-cols-3 gap-3 text-xs">
                        <div>
                          <span className="text-dark-500">样本外夏普</span>
                          <div className="font-mono text-green font-bold">{(iterBest.sharpe_oos ?? 0).toFixed(3)}</div>
                        </div>
                        <div>
                          <span className="text-dark-500">PBO</span>
                          <div className={`font-mono font-bold ${(iterBest.pbo ?? 1) <= 0.3 ? "text-green" : "text-yellow-400"}`}>{(iterBest.pbo ?? 0).toFixed(3)}</div>
                        </div>
                        <div>
                          <span className="text-dark-500">最大回撤</span>
                          <div className="font-mono text-red">{(iterBest.max_drawdown_pct ?? 0).toFixed(1)}%</div>
                        </div>
                      </div>
                      <div className="mt-2 text-xs text-dark-500">
                        策略: {iterBest.strategy_type} | 参数: {JSON.stringify(iterBest.params)}
                      </div>
                      <button
                        onClick={saveToWarehouse}
                        disabled={saving}
                        className="mt-3 w-full py-2 rounded text-xs font-medium bg-green-500/15 text-green border border-green-500/30 hover:bg-green-500/25 transition-all disabled:opacity-50"
                      >
                        {saving ? "保存中..." : "➕ 添加到策略库"}
                      </button>
                    </div>
                  )}

                  {iterError && (
                    <div className="mt-3 px-3 py-2.5 bg-red-500/10 border border-red-500/20 rounded text-xs">
                      <div className="text-red-400 mb-2">{iterError}</div>
                      <button
                        onClick={() => { setIterError(null); startIteration(); }}
                        className="px-3 py-1 rounded text-xs font-medium bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all"
                      >
                        重试迭代
                      </button>
                    </div>
                  )}

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
