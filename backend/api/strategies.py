"""策略管理 API"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from db.models import Strategy, StrategyType, StrategyStatus
from db.database import async_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class StrategyCreate(BaseModel):
    name: str
    type: StrategyType
    symbol: str = "BTC/USDT"
    config: dict = {}


class StrategyUpdate(BaseModel):
    status: Optional[StrategyStatus] = None
    config: Optional[dict] = None


@router.get("/")
async def list_strategies():
    async with async_session() as session:
        result = await session.execute(select(Strategy))
        strategies = result.scalars().all()
        return {"success": True, "data": [
            {
                "id": s.id,
                "name": s.name,
                "type": s.type.value,
                "status": s.status.value,
                "symbol": s.symbol,
                "config": s.config,
                "total_pnl": s.total_pnl,
                "total_trades": s.total_trades,
                "win_rate": s.win_rate,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in strategies
        ]}


@router.post("/")
async def create_strategy(req: StrategyCreate):
    async with async_session() as session:
        strategy = Strategy(
            name=req.name,
            type=req.type,
            symbol=req.symbol,
            config=req.config,
        )
        session.add(strategy)
        await session.commit()
        await session.refresh(strategy)
        return {"success": True, "data": {"id": strategy.id}}


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str):
    async with async_session() as session:
        result = await session.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        s = result.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "not found"}
        return {"success": True, "data": {
            "id": s.id,
            "name": s.name,
            "type": s.type.value,
            "status": s.status.value,
            "symbol": s.symbol,
            "config": s.config,
            "total_pnl": s.total_pnl,
            "total_trades": s.total_trades,
            "win_rate": s.win_rate,
            "sharpe_ratio": s.sharpe_ratio,
            "max_drawdown": s.max_drawdown,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }}


@router.patch("/{strategy_id}")
async def update_strategy(strategy_id: str, req: StrategyUpdate):
    async with async_session() as session:
        result = await session.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        s = result.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "not found"}
        if req.status:
            s.status = req.status
        if req.config:
            s.config = req.config
        await session.commit()
        return {"success": True}


@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: str):
    async with async_session() as session:
        result = await session.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        s = result.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "not found"}
        await session.delete(s)
        await session.commit()
        return {"success": True}
