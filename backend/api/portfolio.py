"""投资组合 API — 薄层：参数校验 → 调用 service → 构造响应"""
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel

from services.portfolio_service import (
    get_portfolio_summary, get_trade_history, get_performance,
    get_positions, get_realtime_assets,
)
from services.portfolio_allocator import portfolio_allocator
from services.trading_service import place_market_order
import core.exchange as exmod
from core.logger import log
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
# 市价平仓
# ------------------------------------------------------------------

class ClosePositionRequest(BaseModel):
    asset: str   # 币种代号，如 "BTC"、"ETH"
    confirm: bool = False  # 必须为 true 才执行


@router.post("/close")
async def close_position(req: ClosePositionRequest, _user: dict = Depends(get_current_user)):
    """市价平仓：对指定币种的现货持仓下达市价卖单。

    自动获取当前持仓数量，以市价单全部卖出。
    需 confirm=true 确认执行。
    """
    if not req.confirm:
        return {"success": False, "error": "需 confirm=true 确认平仓操作"}

    asset = req.asset.upper()
    symbol = f"{asset}/USDT"

    # 获取当前持仓数量
    try:
        balance = exmod.shared_exchange.fetch_balance()
        qty = float(balance.get(asset, {}).get("total", 0) or 0)
        if qty <= 0:
            return {"success": False, "error": f"无 {asset} 持仓"}
    except Exception as e:
        log.error(f"ClosePosition: fetch_balance failed for {asset}: {e}")
        return {"success": False, "error": f"获取持仓失败: {e}"}

    # 下达市价卖单
    order, error, _ = await place_market_order(
        user_id=_user.get("id", "system"),
        symbol=symbol,
        side="sell",
        amount=qty,
        confirm_live=False,
        account_id="default",
        source="manual",
    )
    if error:
        return {"success": False, "error": f"平仓失败: {error}"}

    log.info(f"ClosePosition: {asset} x{qty} sold at market, order={order.get('id') if order else 'N/A'}")

    return {
        "success": True,
        "data": {
            "asset": asset,
            "symbol": symbol,
            "quantity": qty,
            "order": order,
        },
    }


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
