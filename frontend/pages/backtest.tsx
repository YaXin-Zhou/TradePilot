import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import {
  Play, BarChart3, TrendingUp, TrendingDown, RefreshCw,
  Activity, Target, DollarSign, Percent, Hash,
  ShieldCheck, ShieldAlert, AlertTriangle, Divide,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";

const STRATEGIES = [
  { id: "ma_crossover", name: "MA Crossover" },
  { id: "rsi", name: "RSI Mean Reversion" },
  { id: "bollinger", name: "Bollinger Bands" },
];

const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
const TIMEFRAMES = ["1h", "4h", "1d"];

/** 回测参数 — 不同策略使用不同字段子集 */
interface BacktestParams {
  fast?: number;
  slow?: number;
  period?: number;
  oversold?: number;
  overbought?: number;
  std_dev?: number;
  [key: string]: number | undefined;
}

function MetricCard({ icon: Icon, label, value, color, suffix }: any) {
  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} style={{ color }} />
        <span className="text-xs text-dark-400">{label}</span>
      </div>
      <p className="text-lg font-bold font-mono" style={{ color }}>
        {value}{suffix || ""}
      </p>
    </div>
  );
}

function formatTime(ts: any) {
  if (!ts) return "-";
  try { return new Date(ts).toLocaleString(); }
  catch { return String(ts).slice(0, 19); }
}

export default function BacktestPage() {
  const { t, lang } = useLanguage();
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [capital, setCapital] = useState(10000);
  const [positionSize, setPositionSize] = useState(0.95);
  const [tradingFee, setTradingFee] = useState(0.001);
  const [slippage, setSlippage] = useState(0.001);
  const [strategy, setStrategy] = useState("ma_crossover");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [params, setParams] = useState<BacktestParams>({ fast: 10, slow: 30 });

  const runBacktest = async () => {
    setRunning(true);
    setResult(null);
    try {
      const data = await api.runBacktest({
        strategy, symbol, timeframe, limit: 500, capital,
        position_size: positionSize, trading_fee: tradingFee, slippage, params,
      });
      setResult(data);
    } catch (e) {
      console.error("Backtest error:", e);
    }
    setRunning(false);
  };

  const renderParams = () => {
    if (strategy === "ma_crossover") return (
      <div className="grid grid-cols-2 gap-3">
        <div><label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"快线":"Fast MA"}</label>
          <input type="number" value={params.fast} onChange={e => setParams(p=>({...p,fast:+e.target.value}))}
            className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" /></div>
        <div><label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"慢线":"Slow MA"}</label>
          <input type="number" value={params.slow} onChange={e => setParams(p=>({...p,slow:+e.target.value}))}
            className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" /></div>
      </div>
    );
    if (strategy === "rsi") return (
      <div className="grid grid-cols-3 gap-3">
        <div><label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"周期":"Period"}</label>
          <input type="number" value={params.period} onChange={e => setParams(p=>({...p,period:+e.target.value}))}
            className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" /></div>
        <div><label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"超卖":"Oversold"}</label>
          <input type="number" value={params.oversold} onChange={e => setParams(p=>({...p,oversold:+e.target.value}))}
            className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" /></div>
        <div><label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"超买":"Overbought"}</label>
          <input type="number" value={params.overbought} onChange={e => setParams(p=>({...p,overbought:+e.target.value}))}
            className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" /></div>
      </div>
    );
    if (strategy === "bollinger") return (
      <div className="grid grid-cols-2 gap-3">
        <div><label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"周期":"Period"}</label>
          <input type="number" value={params.period} onChange={e => setParams(p=>({...p,period:+e.target.value}))}
            className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" /></div>
        <div><label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"标准差":"Std Dev"}</label>
          <input type="number" value={params.std_dev} onChange={e => setParams(p=>({...p,std_dev:+e.target.value}))}
            step="0.1" className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" /></div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">{t("backtest.title")}</h2>
        <p className="text-xs text-dark-400 mt-1">{t("backtest.subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-4">
          <div className="card">
            <div className="flex items-center gap-2 mb-3">
              <Target size={16} className="text-okx-green" />
              <span className="text-sm font-semibold text-white">{t("backtest.settings")}</span>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-dark-400 block mb-1">{t("trade.symbol")}</label>
                <select value={symbol} onChange={e => setSymbol(e.target.value)}
                  className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200">
                  {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"时间周期":"Timeframe"}</label>
                <select value={timeframe} onChange={e => setTimeframe(e.target.value)}
                  className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200">
                  {TIMEFRAMES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-dark-400 block mb-1">{t("backtest.capital")}</label>
                <input type="number" value={capital} onChange={e => setCapital(+e.target.value)}
                  className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
              </div>
              <div>
                <label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"仓位比例":"Position Size"}</label>
                <input type="number" value={positionSize} onChange={e => setPositionSize(+e.target.value)}
                  min="0.01" max="1" step="0.05"
                  className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
              </div>
              <div>
                <label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"交易费":"Trading Fee"}</label>
                <input type="number" value={tradingFee} onChange={e => setTradingFee(+e.target.value)}
                  min="0" max="0.1" step="0.0005"
                  className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
              </div>
              <div>
                <label className="text-xs text-dark-400 block mb-1">{lang==="zh"?"滑点":"Slippage"}</label>
                <input type="number" value={slippage} onChange={e => setSlippage(+e.target.value)}
                  min="0" max="0.05" step="0.0005"
                  className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200" />
              </div>
              <div>
                <label className="text-xs text-dark-400 block mb-1">{t("strat.type")}</label>
                <select value={strategy} onChange={e => {
                  setStrategy(e.target.value);
                  if (e.target.value === "ma_crossover") setParams({ fast: 10, slow: 30 });
                  else if (e.target.value === "rsi") setParams({ period: 14, oversold: 30, overbought: 70 });
                  else if (e.target.value === "bollinger") setParams({ period: 20, std_dev: 2.0 });
                }}
                  className="w-full text-sm py-1.5 px-2 rounded border border-dark-800 bg-dark-900 text-dark-200">
                  {STRATEGIES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              {renderParams()}
              <button onClick={runBacktest} disabled={running}
                className="btn-primary w-full flex items-center justify-center gap-2 text-sm py-2.5 mt-2">
                {running ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
                {running ? t("backtest.running") : t("backtest.run")}
              </button>
            </div>
          </div>
        </div>

        <div className="lg:col-span-2 space-y-4">
          {!result && !running && (
            <div className="card flex items-center justify-center py-16">
              <div className="text-center">
                <BarChart3 size={48} className="mx-auto mb-3 text-dark-600" />
                <p className="text-sm text-dark-400">{t("backtest.hint")}</p>
              </div>
            </div>
          )}
          {running && (
            <div className="card flex items-center justify-center py-12">
              <RefreshCw size={32} className="text-okx-green animate-spin" />
            </div>
          )}
          {result && !running && (
            <>
              <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
                <MetricCard icon={DollarSign} label={t("backtest.totalReturn")}
                  value={result.total_return.toFixed(2)} color={result.total_return >= 0 ? "#00c076" : "#f6465d"} />
                <MetricCard icon={Percent} label={t("backtest.returnPct")}
                  value={result.total_return_pct.toFixed(2)} color={result.total_return_pct >= 0 ? "#00c076" : "#f6465d"} suffix="%" />
                <MetricCard icon={Activity} label={lang==="zh"?"夏普":"Sharpe"}
                  value={result.sharpe_ratio.toFixed(2)} color={result.sharpe_ratio >= 1 ? "#00c076" : result.sharpe_ratio > 0 ? "#f0b90b" : "#f6465d"} />
                <MetricCard icon={TrendingDown} label={t("backtest.maxDD")}
                  value={result.max_drawdown_pct.toFixed(2)} color="#f6465d" suffix="%" />
                <MetricCard icon={Hash} label={t("backtest.winRate")}
                  value={result.win_rate.toFixed(0)} color="#1e80ff" suffix="%" />
                <MetricCard icon={BarChart3} label={t("backtest.totalTrades")}
                  value={result.total_trades} color="#a855f7" />
              </div>

              {/* ===== Validation Results ===== */}
              {result.validation && !result.validation.error && (
                <div className="space-y-3">
                  {/* Scientific gate banner */}
                  <div className={`card border-l-4 ${result.validation.scientific_passed ? "border-l-okx-green" : "border-l-okx-red"}`}>
                    <div className="flex items-center gap-3">
                      {result.validation.scientific_passed
                        ? <ShieldCheck size={22} className="text-okx-green" />
                        : <ShieldAlert size={22} className="text-okx-red" />
                      }
                      <div>
                        <p className={`text-sm font-semibold ${result.validation.scientific_passed ? "text-okx-green" : "text-okx-red"}`}>
                          {result.validation.scientific_passed ? t("backtest.scientificPassed") : t("backtest.scientificFailed")}
                        </p>
                        <p className="text-xs text-dark-400 mt-0.5">
                          {lang==="zh" ? "五重统计学检验" : "5 statistical tests"} — DSR: {result.validation.dsr?.toFixed(2) || "N/A"} · PBO: {((result.validation.pbo ?? 0) * 100).toFixed(1)}%
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* IS/OOS split comparison */}
                  <div className="card">
                    <div className="flex items-center gap-2 mb-3">
                      <Divide size={14} className="text-okx-yellow" />
                      <span className="text-xs font-semibold text-dark-200">{t("backtest.isOosSplit")}</span>
                      <span className="text-[10px] text-dark-500 ml-auto">{result.validation.is_bars}/{result.validation.oos_bars} bars</span>
                    </div>
                    <div className="grid grid-cols-4 gap-3">
                      <div className="text-center">
                        <p className="text-xs text-dark-400">{t("backtest.sharpeIS")}</p>
                        <p className={`text-base font-mono font-bold mt-0.5 ${result.validation.sharpe_is >= 1 ? "text-okx-green" : result.validation.sharpe_is > 0 ? "text-okx-yellow" : "text-okx-red"}`}>
                          {result.validation.sharpe_is.toFixed(2)}
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-dark-400">{t("backtest.sharpeOOS")}</p>
                        <p className={`text-base font-mono font-bold mt-0.5 ${result.validation.sharpe_oos >= 1 ? "text-okx-green" : result.validation.sharpe_oos > 0 ? "text-okx-yellow" : "text-okx-red"}`}>
                          {result.validation.sharpe_oos.toFixed(2)}
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-dark-400">{t("backtest.maxDdIS")}</p>
                        <p className="text-base font-mono font-bold mt-0.5 text-okx-red">
                          {result.validation.max_dd_is.toFixed(1)}%
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-dark-400">{t("backtest.maxDdOOS")}</p>
                        <p className="text-base font-mono font-bold mt-0.5 text-okx-red">
                          {result.validation.max_dd_oos.toFixed(1)}%
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Overfitting + Significance tests */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="card">
                      <div className="flex items-center gap-2 mb-3">
                        <AlertTriangle size={14} className={result.validation.pbo > 0.5 ? "text-okx-red" : "text-okx-yellow"} />
                        <span className="text-xs font-semibold text-dark-200">{t("backtest.overfitting")}</span>
                      </div>
                      <div className="space-y-2 text-xs">
                        <div className="flex justify-between">
                          <span className="text-dark-400">{t("backtest.pbo")}</span>
                          <span className={`font-mono font-bold ${result.validation.pbo > 0.5 ? "text-okx-red" : result.validation.pbo > 0.3 ? "text-okx-yellow" : "text-okx-green"}`}>
                            {((result.validation.pbo ?? 0) * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-dark-400">{t("backtest.dsr")}</span>
                          <span className={`font-mono font-bold ${result.validation.dsr > 0 ? "text-okx-green" : "text-okx-red"}`}>
                            {result.validation.dsr.toFixed(2)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-dark-400">{t("backtest.totalAttempts")}</span>
                          <span className="font-mono text-white">{result.validation.total_attempts}</span>
                        </div>
                      </div>
                    </div>
                    <div className="card">
                      <div className="flex items-center gap-2 mb-3">
                        <Activity size={14} className="text-blue-400" />
                        <span className="text-xs font-semibold text-dark-200">{t("backtest.significance")}</span>
                      </div>
                      <div className="space-y-2 text-xs">
                        <div className="flex justify-between">
                          <span className="text-dark-400">{t("backtest.nwTStat")}</span>
                          <span className={`font-mono font-bold ${result.validation.nw_t_stat > 1.65 ? "text-okx-green" : "text-okx-red"}`}>
                            {result.validation.nw_t_stat.toFixed(2)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-dark-400">{t("backtest.spaPValue")}</span>
                          <span className={`font-mono font-bold ${result.validation.spa_p_value < 0.05 ? "text-okx-green" : "text-okx-red"}`}>
                            {result.validation.spa_p_value.toFixed(3)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-dark-400">{t("backtest.bhPassed")}</span>
                          <span className={`font-mono font-bold ${result.validation.bh_passed ? "text-okx-green" : "text-okx-red"}`}>
                            {result.validation.bh_passed ? (lang==="zh"?"通过":"PASS") : (lang==="zh"?"未通过":"FAIL")}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Warnings */}
                  {result.validation.warnings && result.validation.warnings.length > 0 && (
                    <div className="card border border-okx-yellow/20 bg-okx-yellow/5">
                      <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle size={14} className="text-okx-yellow" />
                        <span className="text-xs font-semibold text-okx-yellow">{lang==="zh"?"验证警告":"Validation Warnings"}</span>
                      </div>
                      {result.validation.warnings.map((w: string, i: number) => (
                        <p key={i} className="text-xs text-dark-300 leading-relaxed">{w}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Validation error state */}
              {result.validation?.error && (
                <div className="card border-l-4 border-l-okx-yellow">
                  <div className="flex items-center gap-3">
                    <AlertTriangle size={18} className="text-okx-yellow" />
                    <div>
                      <p className="text-sm font-semibold text-okx-yellow">{t("backtest.validationError")}</p>
                      <p className="text-xs text-dark-400 mt-0.5 truncate max-w-md">{result.validation.error}</p>
                    </div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-3 gap-3 text-xs">
                <div className="card">
                  <span className="text-dark-400">{t("backtest.finalCapital")}</span>
                  <p className="font-mono text-white text-sm font-semibold mt-1">${result.final_capital.toFixed(2)}</p>
                </div>
                <div className="card">
                  <span className="text-dark-400">{t("backtest.profitFactor")}</span>
                  <p className="font-mono text-okx-green text-sm font-semibold mt-1">{result.profit_factor.toFixed(2)}</p>
                </div>
                <div className="card">
                  <span className="text-dark-400">{lang==="zh"?"总费用":"Total Fees"}</span>
                  <p className="font-mono text-okx-yellow text-sm font-semibold mt-1">${result.total_fees?.toFixed(2) || "0.00"}</p>
                </div>
                <div className="card">
                  <span className="text-dark-400">{t("strat.type")}</span>
                  <p className="font-mono text-white text-sm font-semibold mt-1">{result.strategy_name}</p>
                </div>
              </div>
              <div className="card">
                <div className="flex items-center gap-2 mb-3">
                  <TrendingUp size={16} className="text-okx-green" />
                  <span className="text-sm font-semibold text-white">{t("backtest.equityCurve")}</span>
                </div>
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={result.equity_curve}>
                    <defs>
                      <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#00c076" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#00c076" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                    <XAxis dataKey="timestamp" tick={{fill:"#848e9c",fontSize:10}}
                      tickFormatter={v => new Date(v).toLocaleDateString()} minTickGap={40} />
                    <YAxis domain={["dataMin - 500", "dataMax + 500"]} tick={{fill:"#848e9c",fontSize:10}} />
                    <Tooltip contentStyle={{background:"#1a1a1a",border:"1px solid #262626",borderRadius:8,fontSize:12}}
                      labelFormatter={v => new Date(v).toLocaleString()}
                      formatter={(val: number) => ["$" + val.toFixed(2), t("backtest.equity")]} />
                    <Area type="monotone" dataKey="equity" stroke="#00c076" fill="url(#eqGrad)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div className="card">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <BarChart3 size={16} className="text-okx-yellow" />
                    <span className="text-sm font-semibold text-white">{t("backtest.tradeLog")}</span>
                  </div>
                  <span className="text-xs text-dark-400">{result.total_trades} {t("backtest.tradesCount")}</span>
                </div>
                {result.trades.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-dark-400 border-b border-dark-800">
                          <th className="text-left py-2 pr-3">{t("backtest.entry")}</th>
                          <th className="text-right px-2 py-2">{t("backtest.entryPrice")}</th>
                          <th className="text-right px-2 py-2">{t("backtest.exit")}</th>
                          <th className="text-right px-2 py-2">{t("backtest.exitPrice")}</th>
                          <th className="text-right px-2 py-2">{t("dash.pnl")}</th>
                          <th className="text-right px-2 py-2">{t("dash.pnlPct")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.trades.map((trade: any, i: number) => (
                          <tr key={i} className="border-b border-dark-800/50 last:border-0 hover:bg-dark-800/30">
                            <td className="py-2 pr-3 text-dark-200">{formatTime(trade.entry_time)}</td>
                            <td className="text-right px-2 py-2 font-mono text-dark-200">${Number(trade.entry_price).toFixed(2)}</td>
                            <td className="text-right px-2 py-2 text-dark-200">{formatTime(trade.exit_time)}</td>
                            <td className="text-right px-2 py-2 font-mono text-dark-200">${Number(trade.exit_price).toFixed(2)}</td>
                            <td className={`text-right px-2 py-2 font-mono ${trade.pnl >= 0 ? "text-okx-green" : "text-okx-red"}`}>
                              {trade.pnl >= 0 ? "+" : ""}${Number(trade.pnl).toFixed(2)}
                            </td>
                            <td className={`text-right px-2 py-2 font-mono ${trade.pnl_pct >= 0 ? "text-okx-green" : "text-okx-red"}`}>
                              {trade.pnl_pct >= 0 ? "+" : ""}{Number(trade.pnl_pct).toFixed(2)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-dark-500">{t("backtest.noTrades")}</div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

