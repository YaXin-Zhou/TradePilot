"""回测 API - 运行和获取回测结果"""
from fastapi import APIRouter, Query
import json, os, pathlib, time as timemod
from core.exchange import ExchangeClient
from config import settings
from strategies.backtest import BacktestEngine
import pandas as pd
import random, math, time

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_exchange = ExchangeClient(
    exchange_name=settings.EXCHANGE_NAME,
    api_key=settings.EXCHANGE_API_KEY,
    secret=settings.EXCHANGE_SECRET,
    passphrase=settings.EXCHANGE_PASSPHRASE,
    testnet=settings.EXCHANGE_TESTNET,
)


def _mock_ohlcv(count=500):
    data = []
    price = 85000
    t = int(time.time() * 1000) - count * 3600000
    for i in range(count):
        change = random.uniform(-400, 400)
        vol = random.uniform(50, 200)
        data.append({
            "timestamp": t / 1000,
            "open": price,
            "high": price + abs(change) + random.uniform(10, 50),
            "low": price - abs(change) - random.uniform(10, 50),
            "close": price + change,
            "volume": vol,
            "symbol": "BTC/USDT",
        })
        price += change * 0.3
        price = max(price, 50000)
        price = min(price, 120000)
        t += 3600000
    return data


def _to_df(ohlcv_data: list) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv_data)
    ts_col = "timestamp"
    if ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col], unit="s", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@router.post("/run")
async def run_backtest(body: dict):
    strategy_type = body.get("strategy", "ma_crossover")
    symbol = body.get("symbol", "BTC/USDT")
    timeframe = body.get("timeframe", "1h")
    limit = body.get("limit", 500)
    capital = float(body.get("capital", 10000))
    params = body.get("params", {})

    # Fetch OHLCV data
    ohlcv = None
    try:
        df = _exchange.fetch_ohlcv(symbol, timeframe, limit)
        if df is not None and len(df) > 0:
            ohlcv = df
    except Exception:
        pass

    if ohlcv is None:
        raw = _mock_ohlcv(limit)
        ohlcv = _to_df(raw)

    if ohlcv is None or len(ohlcv) < 30:
        return {"success": False, "error": "Not enough data for backtest"}

    engine = BacktestEngine(ohlcv, capital)

    try:
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
            return {"success": False, "error": f"Unknown strategy: {strategy_type}"}

        return {
            "success": True,
            "data": {
                "symbol": result.symbol,
                "bars": result.bars,
                "strategy_name": result.strategy_name,
                "strategy_params": result.strategy_params,
                "initial_capital": result.initial_capital,
                "final_capital": result.final_capital,
                "total_return": result.total_return,
                "total_return_pct": result.total_return_pct,
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
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
 
    # Save to history
    try:
        hist_dir = pathlib.Path(__file__).parent.parent / "data"
        hist_dir.mkdir(parents=True, exist_ok=True)
        hist_file = hist_dir / "backtest_history.json"
        records = []
        if hist_file.exists():
            records = json.loads(hist_file.read_text())
        records.insert(0, {
            "id": int(timemod.time()),
            "strategy": strategy_type,
            "symbol": symbol,
            "timeframe": timeframe,
            "capital": capital,
            "params": params,
            "result": {
                "total_return": float(result.total_return),
                "total_return_pct": float(result.total_return_pct),
                "sharpe_ratio": float(result.sharpe_ratio),
                "max_drawdown_pct": float(result.max_drawdown_pct),
                "win_rate": float(result.win_rate),
                "total_trades": int(result.total_trades),
                "profit_factor": float(result.profit_factor),
                "final_capital": float(result.final_capital),
            },
            "created_at": timemod.strftime("%Y-%m-%d %H:%M:%S"),
        })
        records = records[:100]
        hist_file.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    except Exception:
        pass


@router.post("/data")
async def get_backtest_data(body: dict):
    symbol = body.get("symbol", "BTC/USDT")
    timeframe = body.get("timeframe", "1h")
    limit = int(body.get("limit", 500))

    try:
        df = _exchange.fetch_ohlcv(symbol, timeframe, limit)
        if df is not None and len(df) > 0:
            df["timestamp"] = df["timestamp"].astype(int) // 10**9
            records = df.to_dict(orient="records")
            return {"success": True, "data": records}
    except Exception:
        pass

    raw = _mock_ohlcv(limit)
    return {"success": True, "data": raw, "_mock": True}


@router.get("/history")
async def get_backtest_history():
    hist_file = pathlib.Path(__file__).parent.parent / "data" / "backtest_history.json"
    if not hist_file.exists():
        return {"success": True, "data": []}
    try:
        records = json.loads(hist_file.read_text())
        return {"success": True, "data": records}
    except Exception:
        return {"success": True, "data": []}


@router.post("/history/clear")
async def clear_backtest_history():
    hist_file = pathlib.Path(__file__).parent.parent / "data" / "backtest_history.json"
    try:
        hist_file.write_text("[]")
        return {"success": True, "data": {"cleared": True}}
    except Exception:
        return {"success": False, "error": "Failed to clear history"}
