"""回测服务层 — 集成统计验证 + 计数器"""
import json
import time as timemod
import pathlib
import pandas as pd
from core.exchange import ExchangeClient
from config import settings
from strategies.backtest import BacktestEngine
from core.logger import log
from services.validation import run_full_validation

# 独立的 exchange 客户端（回测用，避免抢占 shared_exchange）
_backtest_exchange = ExchangeClient(
    exchange_name=settings.EXCHANGE_NAME,
    api_key=settings.EXCHANGE_API_KEY,
    secret=settings.EXCHANGE_SECRET,
    passphrase=settings.EXCHANGE_PASSPHRASE,
    testnet=settings.EXCHANGE_TESTNET,
)

HISTORY_DIR = pathlib.Path(__file__).parent.parent / "data"
HISTORY_FILE = HISTORY_DIR / "backtest_history.json"
ATTEMPTS_FILE = HISTORY_DIR / "total_attempts.json"


def _to_df(ohlcv_data: list) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv_data)
    ts_col = "timestamp"
    if ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col], unit="s", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> tuple[pd.DataFrame, bool]:
    """获取回测数据。返回 (df, is_mock)。

    v5: 交易所失败时返回空 df + is_mock=True，不再生成随机假数据。
    调用方据 is_mock/空 df 拒绝回测（回测必须用真实行情）。
    """
    try:
        df = _backtest_exchange.fetch_ohlcv(symbol, timeframe, limit)
        if df is not None and len(df) > 0:
            return df, False
    except Exception as e:
        log.warning(f"Backtest OHLCV fetch failed: {e}")

    return pd.DataFrame(), True


# ─── 累计策略尝试次数 ─────────────────────────────────────────


def _load_attempts() -> int:
    """加载累计策略尝试次数"""
    try:
        if ATTEMPTS_FILE.exists():
            data = json.loads(ATTEMPTS_FILE.read_text())
            return data.get("total_attempts", 1)
    except Exception:
        pass
    return 1


def _increment_attempts() -> int:
    """增量 +1 并返回新的 total_attempts"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    current = _load_attempts()
    new_val = current + 1
    ATTEMPTS_FILE.write_text(json.dumps({"total_attempts": new_val}))
    return new_val


def get_total_attempts() -> int:
    """获取当前累计尝试次数"""
    return _load_attempts()


def reset_attempts():
    """重置计数器"""
    ATTEMPTS_FILE.write_text(json.dumps({"total_attempts": 1}))


# ─── 策略回测运行器工厂 ────────────────────────────────────────


def _make_strategy_runner(strategy_type: str):
    """创建策略运行器闭包（供 validation 模块使用）"""
    def runner(df: pd.DataFrame, **params) -> any:
        engine = BacktestEngine(df, 10000, position_size_pct=0.95, trading_fee_pct=0.0005, slippage_pct=0.0005)
        if strategy_type == "ma_crossover":
            return engine.run_ma_crossover(params.get("fast_period", 10), params.get("slow_period", 30))
        elif strategy_type == "rsi":
            return engine.run_rsi(params.get("period", 14), params.get("oversold", 30), params.get("overbought", 70))
        elif strategy_type == "bollinger":
            return engine.run_bollinger(params.get("period", 20), params.get("std_dev", 2.0))
        raise ValueError(f"Unknown strategy: {strategy_type}")
    return runner


# ─── 主入口 ────────────────────────────────────────────────────


def run_backtest(
    ohlcv_df: pd.DataFrame,
    strategy_type: str,
    capital: float,
    params: dict,
    position_size_pct: float = 0.95,
    trading_fee_pct: float = 0.0005,   # v2.1: OKX 永续 taker 0.05%
    slippage_pct: float = 0.0005,
    with_validation: bool = True,
) -> dict:
    """执行回测 + 可选统计验证。返回结果字典"""
    if ohlcv_df is None or len(ohlcv_df) < 30:
        raise ValueError(f"Not enough data for backtest: {len(ohlcv_df) if ohlcv_df is not None else 0} bars")

    engine = BacktestEngine(
        ohlcv_df, capital,
        position_size_pct=position_size_pct,
        trading_fee_pct=trading_fee_pct,
        slippage_pct=slippage_pct,
    )

    if strategy_type == "ma_crossover":
        fast = int(params.get("fast", 10))
        slow = int(params.get("slow", 30))
        result = engine.run_ma_crossover(fast, slow)
    elif strategy_type == "rsi":
        period = int(params.get("period", 14))
        oversold = int(params.get("oversold", 30))
        overbought = int(params.get("overbought", 70))
        result = engine.run_rsi(period, oversold, overbought)
    elif strategy_type == "bollinger":
        period = int(params.get("period", 20))
        std_dev = float(params.get("std_dev", 2.0))
        result = engine.run_bollinger(period, std_dev)
    else:
        raise ValueError(f"Unknown strategy: {strategy_type}")

    base = {
        "symbol": result.symbol,
        "bars": result.bars,
        "strategy_name": result.strategy_name,
        "strategy_params": result.strategy_params,
        "initial_capital": result.initial_capital,
        "final_capital": result.final_capital,
        "total_return": result.total_return,
        "total_return_pct": result.total_return_pct,
        "total_fees": result.total_fees,
        "sharpe_ratio": result.sharpe_ratio,
        "max_drawdown": result.max_drawdown,
        "max_drawdown_pct": result.max_drawdown_pct,
        "win_rate": result.win_rate,
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "avg_win": result.avg_win,
        "avg_loss": result.avg_loss,
        "profit_factor": result.profit_factor,
        "trades": result.trades,
        "equity_curve": result.equity_curve,
    }

    # 统计验证
    if with_validation:
        total_attempts = _increment_attempts()
        try:
            runner = _make_strategy_runner(strategy_type)
            validation = run_full_validation(
                data=ohlcv_df,
                strategy_runner=runner,
                strategy_type=strategy_type,
                params=params,
                equity_curve=result.equity_curve,
                total_attempts=total_attempts,
            )
            base["validation"] = {
                "sharpe_is": validation.sharpe_is,
                "sharpe_oos": validation.sharpe_oos,
                "max_dd_is": validation.max_dd_is,
                "max_dd_oos": validation.max_dd_oos,
                "is_bars": validation.is_bars,
                "oos_bars": validation.oos_bars,
                "pbo": validation.pbo,
                "pbo_warning": validation.pbo_warning,
                "dsr": validation.dsr,
                "total_attempts": total_attempts,
                "nw_se": validation.nw_se,
                "nw_t_stat": validation.nw_t_stat,
                "nw_lags": validation.nw_lags,
                "bh_passed": validation.bh_passed,
                "bh_threshold": validation.bh_threshold,
                "spa_p_value": validation.spa_p_value,
                "spa_passed": validation.spa_passed,
                "scientific_passed": validation.scientific_passed,
                "warnings": validation.warnings,
            }
        except Exception as e:
            log.warning(f"Validation skipped: {e}")
            base["validation"] = {"error": str(e)[:200]}

    return base


# ─── 历史管理 ──────────────────────────────────────────────────


def save_to_history(strategy_type: str, symbol: str, timeframe: str, capital: float, params: dict, result: dict):
    """保存回测结果到历史文件"""
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        records = []
        if HISTORY_FILE.exists():
            records = json.loads(HISTORY_FILE.read_text())
        entry = {
            "id": int(timemod.time()),
            "strategy": strategy_type,
            "symbol": symbol,
            "timeframe": timeframe,
            "capital": capital,
            "params": params,
            "result": {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in {
                "total_return": result.get("total_return", 0),
                "total_return_pct": result.get("total_return_pct", 0),
                "sharpe_ratio": result.get("sharpe_ratio", 0),
                "max_drawdown_pct": result.get("max_drawdown_pct", 0),
                "win_rate": result.get("win_rate", 0),
                "total_trades": result.get("total_trades", 0),
                "profit_factor": result.get("profit_factor", 0),
                "final_capital": result.get("final_capital", 0),
            }.items()},
            "created_at": timemod.strftime("%Y-%m-%d %H:%M:%S"),
        }
        # 附带验证摘要
        if result.get("validation") and not result["validation"].get("error"):
            v = result["validation"]
            entry["validation"] = {
                "sharpe_is": v.get("sharpe_is", 0),
                "sharpe_oos": v.get("sharpe_oos", 0),
                "pbo": v.get("pbo", 0),
                "dsr": v.get("dsr", 0),
                "scientific_passed": v.get("scientific_passed", False),
            }
        records.insert(0, entry)
        HISTORY_FILE.write_text(json.dumps(records[:100], ensure_ascii=False, indent=2))
    except Exception as e:
        log.error(f"Failed to save backtest history: {e}")


def get_history() -> list:
    """获取回测历史"""
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text())
    except Exception:
        return []


def clear_history():
    """清空回测历史"""
    try:
        HISTORY_FILE.write_text("[]")
        reset_attempts()
        return True
    except Exception:
        return False
