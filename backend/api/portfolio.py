"""投资组合 API — 薄层：参数校验 → 调用 service → 构造响应"""
from fastapi import APIRouter, Query

from services.portfolio_service import get_portfolio_summary, get_trade_history, get_performance

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
