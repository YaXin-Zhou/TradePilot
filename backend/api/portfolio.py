"""投资组合 API — 薄层：参数校验 → 调用 service → 构造响应"""
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel

from services.portfolio_service import (
    get_portfolio_summary, get_trade_history, get_performance,
    get_positions, get_realtime_assets,
)
from services.portfolio_allocator import portfolio_allocator
from auth.deps import get_current_user

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary")
async def portfolio_summary():
    return await get_portfolio_summary()


@router.get("/trades")
async def trade_history(limit: int = Query(100, ge=1, le=500)):
    return await get_trade_history(limit)


@router.get("/performance")
async def performance():
    return await get_performance()


@router.get("/positions")
async def positions():
    """获取当前持仓列表（现货模式：非 USDT 币种余额，含浮动盈亏）"""
    return await get_positions()


@router.get("/realtime")
async def realtime_assets():
    """获取实时资金概览 — 总资产/浮动盈亏/24h变化/可用余额"""
    return await get_realtime_assets()


# ------------------------------------------------------------------
# 资金分配
# ------------------------------------------------------------------

class AllocateRequest(BaseModel):
    weights: dict[str, float]
    total_capital: float
    current_positions: dict[str, float] = {}
    regime: str = "RANGING_LOW_VOL"


class RebalanceRequest(BaseModel):
    weights: dict[str, float]
    total_capital: float
    current_positions: dict[str, float] = {}
    regime: str = "RANGING_LOW_VOL"


@router.post("/allocate")
def allocate_capital(req: AllocateRequest, _user: dict = Depends(get_current_user)):
    """渐进式资金分配"""
    plan = portfolio_allocator.allocate(
        req.weights, req.total_capital, req.current_positions, req.regime,
    )
    return {"success": True, "data": plan.to_dict()}


@router.post("/rebalance")
def rebalance_capital(req: RebalanceRequest, _user: dict = Depends(get_current_user)):
    """全量再平衡"""
    plan = portfolio_allocator.rebalance(
        req.weights, req.total_capital, req.current_positions, req.regime,
    )
    return {"success": True, "data": plan.to_dict()}
