"""回测 API — v1.3 U5: +异步回测（后台任务+WebSocket进度推送）"""
import asyncio
import uuid
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.backtest_service import (
    fetch_ohlcv, run_backtest, save_to_history, get_history, clear_history,
    get_total_attempts, reset_attempts,
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
    trading_fee = float(body.get("trading_fee", 0.0005))   # v2.1: OKX 永续 taker 0.05%
    slippage = float(body.get("slippage", 0.0005))
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


@router.get("/stats")
async def api_backtest_stats():
    """查看回测统计：总尝试次数、最近验证通过率"""
    history = get_history()
    total = len(history)
    scientific_passed = sum(1 for h in history if h.get("validation", {}).get("scientific_passed"))
    return {
        "success": True,
        "data": {
            "total_attempts": get_total_attempts(),
            "total_records": total,
            "scientific_passed": scientific_passed,
                "pass_rate": round(scientific_passed / total * 100, 1) if total > 0 else 0,
            },
        }


# ──── v1.3 U5: 异步回测 ────

# 内存任务存储（生产可迁 Redis）
_async_tasks: dict[str, dict] = {}


async def _run_backtest_bg(task_id: str, body: dict):
    """后台执行回测，更新进度并推送 WebSocket"""
    task = _async_tasks.get(task_id)
    if not task:
        return

    task["status"] = "running"

    def _progress(stage: str, pct: int):
        task["progress"] = pct
        task["stage"] = stage

    try:
        _progress("Fetching data", 10)
        ohlcv_df, is_mock = fetch_ohlcv(
            body.get("symbol", "BTC/USDT"),
            body.get("timeframe", "1h"),
            body.get("limit", 500),
        )
        if ohlcv_df is None or len(ohlcv_df) < 30:
            task["status"] = "error"
            task["error"] = f"Not enough data ({len(ohlcv_df) if ohlcv_df is not None else 0} bars)"
            return

        _progress("IS backtest", 30)
        result = run_backtest(
            ohlcv_df,
            body.get("strategy", "ma_crossover"),
            float(body.get("capital", 10000)),
            body.get("params", {}),
            position_size_pct=float(body.get("position_size", 0.95)),
            trading_fee_pct=float(body.get("trading_fee", 0.0005)),
            slippage_pct=float(body.get("slippage", 0.0005)),
            with_validation=True,
        )

        _progress("Validation", 70)
        _progress("Saving result", 90)

        save_to_history(
            body.get("strategy", "ma_crossover"),
            body.get("symbol", "BTC/USDT"),
            body.get("timeframe", "1h"),
            float(body.get("capital", 10000)),
            body.get("params", {}),
            result,
        )

        _progress("Complete", 100)
        task["status"] = "done"
        task["result"] = {"success": True, "data": result}
        if is_mock:
            task["result"]["_mock"] = True

    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)


@router.post("/async")
async def api_run_backtest_async(body: dict):
    """v1.3 U5: 异步回测 — POST 立即返回 task_id，后台执行"""
    task_id = f"bt_{uuid.uuid4().hex[:12]}"
    _async_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "stage": "Queued",
        "created_at": time.time(),
        "result": None,
        "error": None,
    }
    asyncio.create_task(_run_backtest_bg(task_id, body))
    return {"success": True, "data": {"task_id": task_id, "status": "pending"}}


@router.get("/async/{task_id}")
async def api_backtest_status(task_id: str):
    """v1.3 U5: 查询异步回测状态/结果"""
    task = _async_tasks.get(task_id)
    if not task:
        return {"success": False, "error": "Task not found"}
    return {"success": True, "data": task}


@router.websocket("/ws/{task_id}")
async def ws_backtest_progress(websocket: WebSocket, task_id: str):
    """v1.3 U5: WebSocket 回测进度推送"""
    await websocket.accept()
    try:
        while True:
            task = _async_tasks.get(task_id)
            if not task:
                await websocket.send_json({"error": "Task not found"})
                break

            await websocket.send_json({
                "progress": task["progress"],
                "stage": task["stage"],
                "status": task["status"],
            })

            if task["status"] in ("done", "error"):
                if task["status"] == "done":
                    await websocket.send_json(task["result"])
                else:
                    await websocket.send_json({"error": task.get("error", "Unknown")})
                break

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
