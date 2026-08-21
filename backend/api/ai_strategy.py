"""AI Strategy API — 薄层：参数校验 → 调用 service → 构造响应"""
import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel

from auth.deps import get_current_user
from services.ai_service import analyze_market, test_ai_connection
from services.ai_iterator import start_iteration, get_task_status, list_tasks, get_best_variant

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AnalyzeRequest(BaseModel):
    auto: bool = False
    name: str = ""
    strategy_desc: str = ""
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"


class IterateRequest(BaseModel):
    goal: str
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    variants: int = 10
    max_rounds: int = 5
    capital: float = 10000
    risk_constraints: dict | None = None


@router.post("/analyze")
async def ai_analyze(req: AnalyzeRequest, _user: dict = Depends(get_current_user)):
    from core.logger import log
    log.info(f"[AI_DEBUG] Route entered, symbol={req.symbol}, auto={req.auto}")
    try:
        log.info(f"[AI_DEBUG] About to call analyze_market...")
        result = await analyze_market(
            symbol=req.symbol,
            timeframe=req.timeframe,
            auto=req.auto,
            strategy_desc=req.strategy_desc,
            name=req.name,
            user_id=_user.get("id", ""),
        )
        log.info(f"[AI_DEBUG] analyze_market returned: success={result.get('success')}")
        return result
    except Exception as e:
        import traceback
        log.error(f"[AI_DEBUG] AI analyze exception: {type(e).__name__}: {str(e)[:200]}\n{traceback.format_exc()}")
        return {"success": False, "error": str(e)[:200]}


@router.post("/iterate")
async def ai_iterate(req: IterateRequest, background_tasks: BackgroundTasks):
    """启动 AI 策略迭代任务（后台运行）"""
    if not req.goal.strip():
        return {"success": False, "error": "Goal is required"}
    if req.variants < 1 or req.variants > 50:
        return {"success": False, "error": "variants must be 1-50"}
    if req.max_rounds < 1 or req.max_rounds > 10:
        return {"success": False, "error": "max_rounds must be 1-10"}

    import time, json
    from sqlalchemy import text
    from db.database import async_session

    task_id = f"iter_{int(time.time() * 1000)}"

    # 先同步写入任务记录（前端立即轮询不会丢）
    try:
        async with async_session() as session:
            await session.execute(
                text("""
                    INSERT INTO iteration_tasks (task_id, status, goal, symbol, timeframe,
                        max_rounds, current_round, total_variants, scientific_passed,
                        created_at, updated_at)
                    VALUES (:tid, 'pending', :goal, :sym, :tf, :mr, 0, 0, 0, now(), now())
                """),
                {"tid": task_id, "goal": req.goal.strip(), "sym": req.symbol,
                 "tf": req.timeframe, "mr": req.max_rounds},
            )
            await session.commit()
    except Exception as e:
        from core.logger import log
        log.error(f"Failed to create iteration task record: {e}")

    # 后台启动迭代
    risk = req.risk_constraints or {"max_drawdown_pct": 20, "min_sharpe": 0.8, "max_concentration": 0.3}

    # 后台启动迭代
    async def _run_iteration():
        try:
            await start_iteration(
                task_id=task_id,
                goal=req.goal.strip(),
                symbol=req.symbol,
                timeframe=req.timeframe,
                variants=req.variants,
                max_rounds=req.max_rounds,
                risk_constraints=risk,
                capital=req.capital,
            )
        except Exception as e:
            import traceback
            from core.logger import log
            log.error(f"Iteration background task failed: {e}\n{traceback.format_exc()}")

    background_tasks.add_task(_run_iteration)
    return {"success": True, "data": {"task_id": task_id, "goal": req.goal}}


class SaveToWarehouseRequest(BaseModel):
    strategy_type: str
    params: dict
    symbol: str = "BTC/USDT"
    metrics: dict = {}  # {sharpe_oos, max_drawdown_pct, win_rate, total_trades, ...}

@router.post("/iterate/save-to-warehouse")
async def save_iteration_to_warehouse(req: SaveToWarehouseRequest, _user: dict = Depends(get_current_user)):
    """将迭代产出的达标策略手动保存到策略库（v6 3.1: 仅存草稿，不自动入池，需人工注册启用）"""
    from datetime import datetime
    from services.strategy_service import save_ai_strategy

    auto_name = f"Iter-{req.strategy_type}-{req.symbol.replace('/', '')}-{datetime.now().strftime('%m%d%H%M')}"
    backtest = {
        "sharpe_ratio": req.metrics.get("sharpe_oos", 0),
        "max_drawdown_pct": req.metrics.get("max_drawdown_pct", 0),
        "win_rate": req.metrics.get("win_rate", 0),
        "total_trades": req.metrics.get("total_trades", 0),
        "total_return_pct": req.metrics.get("total_return_pct", 0),
    }
    result = await save_ai_strategy(
        name=auto_name, strategy_type=req.strategy_type, symbol=req.symbol,
        config=req.params, backtest=backtest, user_id=_user.get("id", ""),
    )
    if result.get("success"):
        sid = result["data"]["id"]
        # v6 3.1: 保存为 DRAFT，不入池；前端引导用户经 /api/strategies/pool/{id}/register 手动启用
        return {"success": True, "data": {"strategy_id": sid, "name": auto_name, "draft": True}}
    return result


@router.get("/iterate/status/{task_id}")
async def iteration_status(task_id: str):
    """查询迭代任务状态"""
    status = await get_task_status(task_id)
    if status is None:
        return {"success": False, "error": "Task not found"}
    return {"success": True, "data": status}


@router.get("/iterate/best/{task_id}")
async def iteration_best(task_id: str):
    """获取迭代任务的最优策略"""
    best = await get_best_variant(task_id)
    if best is None:
        return {"success": False, "error": "No results yet"}
    return {"success": True, "data": best}


@router.get("/iterate/tasks")
async def iteration_tasks(limit: int = 20):
    """列出最近的迭代任务"""
    tasks = await list_tasks(limit)
    return {"success": True, "data": tasks}


@router.post("/test-connection")
async def test_connection():
    return await test_ai_connection()
