"""策略管理 API"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from db.models import Strategy, StrategyType, StrategyStatus
from strategies.runner import runner
from strategies.custom import CustomStrategy
from db.database import async_session
from sqlalchemy import select
from auth.deps import get_current_user
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
async def create_strategy(req: StrategyCreate, _user: dict = Depends(get_current_user)):
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
async def update_strategy(strategy_id: str, req: StrategyUpdate, _user: dict = Depends(get_current_user)):
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


@router.post("/{strategy_id}/start")
async def start_strategy(strategy_id: str, _user: dict = Depends(get_current_user)):
    async with async_session() as session:
        r = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
        s = r.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "not found"}
        if s.type == StrategyType.CUSTOM:
            instance = CustomStrategy(s.id, s.name, s.config)
        elif s.type == StrategyType.GRID:
            from strategies.grid import GridStrategy
            instance = GridStrategy(s.id, s.name, s.config)
        else:
            return {"success": False, "error": "unsupported type"}
        await runner.start(strategy_id, instance)
        s.status = StrategyStatus.RUNNING
        s.started_at = datetime.now(timezone.utc)
        await session.commit()
    return {"success": True}


@router.post("/{strategy_id}/stop")
async def stop_strategy(strategy_id: str, _user: dict = Depends(get_current_user)):
    await runner.stop(strategy_id)
    return {"success": True}



@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: str, _user: dict = Depends(get_current_user)):
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


