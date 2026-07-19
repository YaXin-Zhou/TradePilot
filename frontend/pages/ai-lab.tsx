import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import {
  FlaskConical, Target, Play, RefreshCw, ShieldCheck, ShieldAlert,
  Activity, TrendingUp, DollarSign, BarChart3, Clock, Zap, ChevronRight,
} from "lucide-react";

export default function AILabPage() {
  const { t, lang } = useLanguage();
  const [goal, setGoal] = useState("");
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [variants, setVariants] = useState(10);
  const [maxRounds, setMaxRounds] = useState(5);
  const [maxDrawdown, setMaxDrawdown] = useState(20);
  const [minSharpe, setMinSharpe] = useState(0.8);
  const [maxConcentration, setMaxConcentration] = useState(0.3);
  const [running, setRunning] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskData, setTaskData] = useState<any>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // Poll status
  useEffect(() => {
    if (!taskId || !running) return;
    const timer = setInterval(async () => {
      try {
        const data = await api.getIterationStatus(taskId);
        setTaskData(data);
        if (data.status === "completed" || data.status === "failed") {
          setRunning(false);
        }
      } catch {}
    }, 3000);
    return () => clearInterval(timer);
  }, [taskId, running]);

  // Load history
  const loadHistory = useCallback(async () => {
    try {
      const data = await api.listIterationTasks(20);
      setTasks(data || []);
    } catch {}
  }, []);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  const startIteration = async () => {
    if (!goal.trim()) return;
    setRunning(true);
    setTaskData(null);
    try {
      await api.startIteration({
        goal: goal.trim(),
        symbol,
        timeframe,
        variants,
        max_rounds: maxRounds,
        risk_constraints: {
          max_drawdown_pct: maxDrawdown,
          min_sharpe: minSharpe,
          max_concentration: maxConcentration,
        },
      });
      // Wait a bit then start polling for the first task_id
      setTimeout(async () => {
        try {
          const data = await api.listIterationTasks(1);
          if (data && data.length > 0) {
            setTaskId(data[0].task_id);
            setTaskData(data[0]);
          }
        } catch {}
      }, 2000);
    } catch {
      setRunning(false);
    }
  };

  const viewTask = async (id: string) => {
    setTaskId(id);
    setRunning(true);
    setShowHistory(false);
    try {
      const data = await api.getIterationStatus(id);
      setTaskData(data);
      if (data.status === "completed" || data.status === "failed") {
        setRunning(false);
      }
    } catch {
      setRunning(false);
    }
  };

  const statusBadge = (status: string) => {
    const colors: any = {
      pending: "bg-dark-500 text-dark-300",
      running: "bg-blue-500/20 text-blue-400",
      generating: "bg-purple-500/20 text-purple-400",
      backtesting: "bg-okx-yellow/20 text-okx-yellow",
      done: "bg-okx-green/20 text-okx-green",
      completed: "bg-okx-green/20 text-okx-green",
      failed: "bg-okx-red/20 text-okx-red",
    };
    return (
      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${colors[status] || "bg-dark-500 text-dark-300"}`}>
        {status}
      </span>
    );
  };

  const renderBestVariant = (v: any) => (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Zap size={14} className="text-okx-green" />
        <span className="text-xs font-semibold text-dark-200">
          {v.strategy_type?.replace("_", " ").toUpperCase()}
        </span>
        {v.scientific_passed
          ? <ShieldCheck size={14} className="text-okx-green" />
          : <ShieldAlert size={14} className="text-okx-red" />}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-dark-800/50 rounded p-2">
          <p className="text-dark-400">Sharpe IS</p>
          <p className={`font-mono font-bold ${v.sharpe_is >= 1 ? "text-okx-green" : "text-okx-yellow"}`}>
            {v.sharpe_is?.toFixed(2)}
          </p>
        </div>
        <div className="bg-dark-800/50 rounded p-2">
          <p className="text-dark-400">Sharpe OOS</p>
          <p className={`font-mono font-bold ${v.sharpe_oos >= 1 ? "text-okx-green" : "text-okx-yellow"}`}>
            {v.sharpe_oos?.toFixed(2)}
          </p>
        </div>
        <div className="bg-dark-800/50 rounded p-2">
          <p className="text-dark-400">Return %</p>
          <p className={`font-mono font-bold ${v.total_return_pct >= 0 ? "text-okx-green" : "text-okx-red"}`}>
            {v.total_return_pct?.toFixed(1)}%
          </p>
        </div>
        <div className="bg-dark-800/50 rounded p-2">
          <p className="text-dark-400">Max DD %</p>
          <p className="font-mono font-bold text-okx-red">{v.max_drawdown_pct?.toFixed(1)}%</p>
        </div>
        <div className="bg-dark-800/50 rounded p-2">
          <p className="text-dark-400">PBO</p>
          <p className={`font-mono font-bold ${v.pbo <= 0.5 ? "text-okx-green" : "text-okx-red"}`}>
            {((v.pbo ?? 0) * 100).toFixed(1)}%
          </p>
        </div>
        <div className="bg-dark-800/50 rounded p-2">
          <p className="text-dark-400">DSR</p>
          <p className={`font-mono font-bold ${v.dsr > 0 ? "text-okx-green" : "text-okx-red"}`}>
            {v.dsr?.toFixed(2)}
          </p>
        </div>
      </div>

      <div className="bg-dark-800/30 rounded p-2">
        <p className="text-[10px] text-dark-400 mb-1">Parameters</p>
        <pre className="text-xs font-mono text-dark-200">{JSON.stringify(v.params, null, 2)}</pre>
      </div>

      {v.rationale && (
        <div className="bg-dark-800/30 rounded p-2">
          <p className="text-[10px] text-dark-400 mb-1">Rationale</p>
          <p className="text-xs text-dark-300">{v.rationale}</p>
        </div>
      )}

      <div className="flex gap-2">
        <div className="text-center flex-1 bg-dark-800/50 rounded p-2">
          <p className="text-[10px] text-dark-400">{lang==="zh"?"综合评分":"Score"}</p>
          <p className="font-mono font-bold text-okx-green text-sm">{v.score?.toFixed(3)}</p>
        </div>
        <div className="text-center flex-1 bg-dark-800/50 rounded p-2">
          <p className="text-[10px] text-dark-400">Win Rate</p>
          <p className="font-mono font-bold text-blue-400 text-sm">{v.win_rate?.toFixed(0)}%</p>
        </div>
        <div className="text-center flex-1 bg-dark-800/50 rounded p-2">
          <p className="text-[10px] text-dark-400">Trades</p>
          <p className="font-mono font-bold text-white text-sm">{v.total_trades || 0}</p>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">{t("ailab.title")}</h2>
        <p className="text-xs text-dark-400 mt-1">{t("ailab.subtitle")}</p>
      </div>

      <div className="flex gap-2">
        <button onClick={() => setShowHistory(false)}
          className={`text-xs px-3 py-1.5 rounded ${!showHistory ? "bg-okx-green/20 text-okx-green" : "bg-dark-800 text-dark-400"}`}>
          {lang==="zh"?"新建任务":"New Task"}
        </button>
        <button onClick={() => { setShowHistory(true); loadHistory(); }}
          className={`text-xs px-3 py-1.5 rounded ${showHistory ? "bg-okx-green/20 text-okx-green" : "bg-dark-800 text-dark-400"}`}>
          {t("ailab.history")} ({tasks.length})
        </button>
      </div>

      {showHistory ? (
        /* History view */
        <div className="space-y-3">
          {tasks.length === 0 ? (
            <div className="card text-center py-12 text-dark-500 text-xs">No tasks yet</div>
          ) : (
            tasks.map((t: any) => (
              <div key={t.task_id} className="card flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <p className="text-sm text-white font-semibold truncate">{t.goal}</p>
                    {statusBadge(t.status)}
                  </div>
                  <p className="text-[10px] text-dark-400">
                    {t.symbol} {t.timeframe} · {t.current_round}/{t.max_rounds} rounds · {t.total_variants} variants
                    {t.converged && <span className="text-okx-green ml-2">{t("ailab.converged")}</span>}
                  </p>
                </div>
                <button onClick={() => viewTask(t.task_id)}
                  className="text-xs text-okx-green hover:text-okx-green/80 flex items-center gap-1 ml-4">
                  {t("ailab.viewDetail")} <ChevronRight size={12} />
                </button>
              </div>
            ))
          )}
        </div>
      ) : (
        /* Main 3-column lab */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left: Settings */}
          <div className="lg:col-span-3 space-y-4">
            <div className="card">
              <div className="flex items-center gap-2 mb-3">
                <Target size={16} className="text-okx-green" />
                <span className="text-sm font-semibold text-white">{t("ailab.goal")}</span>
              </div>
              <textarea value={goal} onChange={e => setGoal(e.target.value)}
                placeholder={t("ailab.goalPlaceholder")}
                rows={3}
                className="w-full text-sm py-2 px-3 rounded border border-dark-800 bg-dark-900 text-dark-200 resize-none placeholder:text-dark-600" />
              <div className="grid grid-cols-2 gap-2 mt-3">
                <div>
                  <label className="text-[10px] text-dark-400 block mb-1">Symbol</label>
                  <select value={symbol} onChange={e => setSymbol(e.target.value)}
                    className="w-full text-xs py-1 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200">
                    {["BTC/USDT","ETH/USDT","SOL/USDT"].map(s=><option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-dark-400 block mb-1">Timeframe</label>
                  <select value={timeframe} onChange={e => setTimeframe(e.target.value)}
                    className="w-full text-xs py-1 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200">
                    {["1h","4h","1d"].map(t=><option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="flex items-center gap-2 mb-3">
                <ShieldAlert size={14} className="text-okx-yellow" />
                <span className="text-sm font-semibold text-white">{t("ailab.constraints")}</span>
              </div>
              <div className="space-y-2">
                <div>
                  <label className="text-[10px] text-dark-400 block mb-0.5">{t("ailab.maxDrawdown")}</label>
                  <input type="number" value={maxDrawdown} onChange={e => setMaxDrawdown(+e.target.value)}
                    className="w-full text-xs py-1 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
                </div>
                <div>
                  <label className="text-[10px] text-dark-400 block mb-0.5">{t("ailab.minSharpe")}</label>
                  <input type="number" value={minSharpe} onChange={e => setMinSharpe(+e.target.value)}
                    step="0.1" min="0"
                    className="w-full text-xs py-1 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
                </div>
                <div>
                  <label className="text-[10px] text-dark-400 block mb-0.5">{t("ailab.maxConcentration")}</label>
                  <input type="number" value={maxConcentration} onChange={e => setMaxConcentration(+e.target.value)}
                    step="0.1" min="0" max="1"
                    className="w-full text-xs py-1 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
                </div>
              </div>
            </div>

            <div className="card">
              <div className="grid grid-cols-2 gap-2 mb-3">
                <div>
                  <label className="text-[10px] text-dark-400 block mb-0.5">{t("ailab.variants")}</label>
                  <input type="number" value={variants} onChange={e => setVariants(+e.target.value)}
                    min={1} max={50}
                    className="w-full text-xs py-1 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
                </div>
                <div>
                  <label className="text-[10px] text-dark-400 block mb-0.5">{t("ailab.maxRounds")}</label>
                  <input type="number" value={maxRounds} onChange={e => setMaxRounds(+e.target.value)}
                    min={1} max={10}
                    className="w-full text-xs py-1 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
                </div>
              </div>
              <button onClick={startIteration} disabled={running || !goal.trim()}
                className="btn-primary w-full flex items-center justify-center gap-2 text-sm py-2.5">
                {running ? <RefreshCw size={14} className="animate-spin" /> : <FlaskConical size={14} />}
                {running ? t("ailab.starting") : t("ailab.start")}
              </button>
            </div>
          </div>

          {/* Middle: Progress */}
          <div className="lg:col-span-5">
            <div className="card h-full">
              <div className="flex items-center gap-2 mb-4">
                <Activity size={16} className="text-blue-400" />
                <span className="text-sm font-semibold text-white">{t("ailab.progress")}</span>
                {taskData && statusBadge(taskData.status)}
              </div>

              {!taskData ? (
                <div className="flex items-center justify-center py-20">
                  <div className="text-center">
                    <FlaskConical size={48} className="mx-auto mb-3 text-dark-600" />
                    <p className="text-sm text-dark-400">{t("ailab.noResult")}</p>
                    <p className="text-xs text-dark-600 mt-1">{t("ailab.noResultHint")}</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Progress bar */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-dark-400">{taskData.current_round}/{taskData.max_rounds} rounds</span>
                      <span className="text-dark-400">{taskData.total_variants} variants</span>
                    </div>
                    <div className="w-full bg-dark-800 rounded-full h-2">
                      <div className="bg-okx-green h-2 rounded-full transition-all duration-500"
                        style={{width: `${taskData.progress_pct || (taskData.current_round / taskData.max_rounds * 100)}%`}} />
                    </div>
                  </div>

                  {/* Stats row */}
                  <div className="grid grid-cols-3 gap-2">
                    <div className="bg-dark-800/50 rounded p-2 text-center">
                      <p className="text-[10px] text-dark-400">{t("ailab.variantsDone").replace("{n}", taskData.total_variants || "0")}</p>
                      <p className="font-mono font-bold text-white text-sm">{taskData.total_variants || 0}</p>
                    </div>
                    <div className="bg-dark-800/50 rounded p-2 text-center">
                      <p className="text-[10px] text-dark-400">{lang==="zh"?"科学验证":"Scientific"}</p>
                      <p className="font-mono font-bold text-okx-green text-sm">{taskData.scientific_passed || 0}</p>
                    </div>
                    <div className="bg-dark-800/50 rounded p-2 text-center">
                      <p className="text-[10px] text-dark-400">{t("ailab.topScore")}</p>
                      <p className="font-mono font-bold text-okx-yellow text-sm">
                        {taskData.rounds?.length > 0 ? taskData.rounds[taskData.rounds.length-1].top_score?.toFixed(3) || "-" : "-"}
                      </p>
                    </div>
                  </div>

                  {/* Convergence */}
                  {taskData.converged && (
                    <div className="bg-okx-green/10 border border-okx-green/20 rounded p-3">
                      <p className="text-xs text-okx-green font-semibold">{t("ailab.converged")}</p>
                      <p className="text-[10px] text-dark-400 mt-0.5">{taskData.convergence_reason}</p>
                    </div>
                  )}

                  {/* Rounds list */}
                  {taskData.rounds?.length > 0 && (
                    <div className="space-y-2 max-h-80 overflow-y-auto">
                      {taskData.rounds.map((rd: any, i: number) => {
                        const variants = rd.variants || [];
                        const ranked = [...variants].sort((a:any,b:any) => (b.score||0) - (a.score||0));
                        return (
                          <div key={i} className="bg-dark-800/30 rounded p-3">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs font-semibold text-dark-200">
                                {t("ailab.round").replace("{n}", rd.round_number)}
                              </span>
                              {statusBadge(rd.status)}
                            </div>
                            <div className="text-[10px] text-dark-400 mb-2">
                              {ranked.length} variants · Top Sharpe OOS: {rd.top_sharpe_oos?.toFixed(2)}
                            </div>
                            {/* Top 3 variants */}
                            <div className="space-y-1">
                              {ranked.slice(0, 3).map((v: any, j: number) => (
                                <div key={j} className="flex items-center justify-between text-[10px]">
                                  <div className="flex items-center gap-1.5">
                                    <span className={`font-mono ${j===0 ? "text-okx-yellow" : "text-dark-500"}`}>#{j+1}</span>
                                    <span className="text-dark-300">{v.strategy_type}</span>
                                    <span className="text-dark-500">{JSON.stringify(v.params)}</span>
                                  </div>
                                  <div className="flex items-center gap-2 font-mono">
                                    <span className={v.sharpe_oos >= 1 ? "text-okx-green" : "text-dark-400"}>
                                      OOS:{v.sharpe_oos?.toFixed(2)}
                                    </span>
                                    <span className="text-okx-yellow">{v.score?.toFixed(3)}</span>
                                    {v.scientific_passed
                                      ? <ShieldCheck size={10} className="text-okx-green" />
                                      : <span className="text-dark-500">-</span>}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Right: Best Strategy */}
          <div className="lg:col-span-4">
            <div className="card h-full">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp size={16} className="text-okx-green" />
                <span className="text-sm font-semibold text-white">{t("ailab.bestStrategy")}</span>
              </div>

              {(!taskData || !taskData.best_variant) ? (
                <div className="flex items-center justify-center py-20">
                  <div className="text-center">
                    <Zap size={48} className="mx-auto mb-3 text-dark-600" />
                    <p className="text-xs text-dark-500">{lang==="zh"?"完成迭代后显示":"Shows after iteration"}</p>
                  </div>
                </div>
              ) : (
                renderBestVariant(taskData.best_variant)
              )}

              {/* Error display */}
              {taskData?.error && (
                <div className="mt-4 bg-okx-red/10 border border-okx-red/20 rounded p-3">
                  <p className="text-xs text-okx-red font-semibold">{t("ailab.failed")}</p>
                  <p className="text-[10px] text-dark-400 mt-1 truncate">{taskData.error}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
