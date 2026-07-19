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
    return await analyze_market(
        symbol=req.symbol,
        timeframe=req.timeframe,
        auto=req.auto,
        strategy_desc=req.strategy_desc,
    )


@router.post("/iterate")
async def ai_iterate(req: IterateRequest, background_tasks: BackgroundTasks):
    """启动 AI 策略迭代任务（后台运行）"""
    if not req.goal.strip():
        return {"success": False, "error": "Goal is required"}
    if req.variants < 1 or req.variants > 50:
        return {"success": False, "error": "variants must be 1-50"}
    if req.max_rounds < 1 or req.max_rounds > 10:
        return {"success": False, "error": "max_rounds must be 1-10"}

    # 后台启动迭代
    background_tasks.add_task(
        asyncio.create_task,
        start_iteration(
            goal=req.goal.strip(),
            symbol=req.symbol,
            timeframe=req.timeframe,
            variants=req.variants,
            max_rounds=req.max_rounds,
            risk_constraints=req.risk_constraints,
            capital=req.capital,
        ),
    )
    return {"success": True, "message": "Iteration task started", "data": {"goal": req.goal}}


@router.get("/iterate/status/{task_id}")
async def iteration_status(task_id: str):
    """查询迭代任务状态"""
    status = get_task_status(task_id)
    if status is None:
        return {"success": False, "error": "Task not found"}
    return {"success": True, "data": status}


@router.get("/iterate/best/{task_id}")
async def iteration_best(task_id: str):
    """获取迭代任务的最优策略"""
    best = get_best_variant(task_id)
    if best is None:
        return {"success": False, "error": "No results yet"}
    return {"success": True, "data": best}


@router.get("/iterate/tasks")
async def iteration_tasks(limit: int = 20):
    """列出最近的迭代任务"""
    tasks = list_tasks(limit)
    return {"success": True, "data": tasks}


@router.post("/test-connection")
async def test_connection():
    return await test_ai_connection()
