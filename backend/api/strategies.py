"""策略管理 API — 薄层：参数校验 → 调用 service → 构造响应"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from db.models import StrategyType, StrategyStatus
from auth.deps import get_current_user
from services.strategy_service import (
    list_all_strategies,
    create_strategy,
    get_strategy_detail,
    update_strategy,
    start_strategy,
    stop_strategy,
    delete_strategy,
)

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
    return {"success": True, "data": await list_all_strategies()}


@router.post("/")
async def api_create_strategy(req: StrategyCreate, _user: dict = Depends(get_current_user)):
    return await create_strategy(req.name, req.type, req.symbol, req.config)


@router.get("/{strategy_id}")
async def api_get_strategy(strategy_id: str):
    return await get_strategy_detail(strategy_id)


@router.patch("/{strategy_id}")
async def api_update_strategy(strategy_id: str, req: StrategyUpdate, _user: dict = Depends(get_current_user)):
    return await update_strategy(strategy_id, req.status, req.config)


@router.post("/{strategy_id}/start")
async def api_start_strategy(strategy_id: str, _user: dict = Depends(get_current_user)):
    return await start_strategy(strategy_id)


@router.post("/{strategy_id}/stop")
async def api_stop_strategy(strategy_id: str, _user: dict = Depends(get_current_user)):
    return await stop_strategy(strategy_id)


@router.delete("/{strategy_id}")
async def api_delete_strategy(strategy_id: str, _user: dict = Depends(get_current_user)):
    return await delete_strategy(strategy_id)
