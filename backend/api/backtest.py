"""回测 API"""
from fastapi import APIRouter
from services.backtest_service import (
    fetch_ohlcv, run_backtest, save_to_history, get_history, clear_history,
    _mock_ohlcv, _to_df,
)
import pandas as pd

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("/run")
async def api_run_backtest(body: dict):
    strategy_type = body.get("strategy", "ma_crossover")
    symbol = body.get("symbol", "BTC/USDT")
    timeframe = body.get("timeframe", "1h")
    limit = body.get("limit", 500)
    capital = float(body.get("capital", 10000))
    position_size = float(body.get("position_size", 0.95))
    trading_fee = float(body.get("trading_fee", 0.001))
    slippage = float(body.get("slippage", 0.001))
    params = body.get("params", {})

    # 获取数据
    ohlcv_df, is_mock = fetch_ohlcv(symbol, timeframe, limit)

    if ohlcv_df is None or len(ohlcv_df) < 30:
        return {"success": False, "error": f"Not enough data ({len(ohlcv_df) if ohlcv_df is not None else 0} bars)"}

    try:
        result = run_backtest(ohlcv_df, strategy_type, capital, params, position_size, trading_fee, slippage)
    except Exception as e:
        return {"success": False, "error": str(e)}

    # 保存到历史
    save_to_history(strategy_type, symbol, timeframe, capital, params, result)

    resp = {"success": True, "data": result}
    if is_mock:
        resp["_mock"] = True
    return resp


@router.post("/data")
async def api_backtest_data(body: dict):
    symbol = body.get("symbol", "BTC/USDT")
    timeframe = body.get("timeframe", "1h")
    limit = int(body.get("limit", 500))

    ohlcv_df, is_mock = fetch_ohlcv(symbol, timeframe, limit)
    if is_mock:
        raw = _mock_ohlcv(limit)
        return {"success": True, "data": raw, "_mock": True}

    ohlcv_df["timestamp"] = ohlcv_df["timestamp"].astype(int) // 10**9
    records = ohlcv_df.to_dict(orient="records")
    return {"success": True, "data": records}


@router.get("/history")
async def api_backtest_history():
    return {"success": True, "data": get_history()}


@router.post("/history/clear")
async def api_clear_history():
    ok = clear_history()
    if ok:
        return {"success": True, "data": {"cleared": True}}
    return {"success": False, "error": "Failed to clear history"}
