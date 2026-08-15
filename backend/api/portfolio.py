"""投资组合 API — 薄层：参数校验 → 调用 service → 构造响应"""
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel

from services.portfolio_service import (
    get_portfolio_summary, get_trade_history, get_performance,
    get_positions, get_realtime_assets,
)
from services.portfolio_allocator import portfolio_allocator
import core.exchange as exmod
from core.logger import log
from auth.deps import get_current_user
from db.database import async_session
from db.models import Trade

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _utcnow_naive() -> datetime:
    """统一返回 naive UTC datetime（与 DB TIMESTAMP WITHOUT TIME ZONE 兼容）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _record_manual_close(symbol: str, side: str, contracts: float,
                               entry_price: float, exit_price: float, order: dict):
    """手动平仓后写入 Trade 表（V5 问题2：此前手动平仓不落库，仪表盘「最近成交」恒为空）。

    strategy_id 置 None 表示非策略手动交易；数量单位是「张数」，盈亏需乘 contractSize。
    """
    try:
        if contracts <= 0:
            return
        cs = exmod.shared_exchange.get_contract_size(symbol)
        if side == "long":
            profit = (exit_price - entry_price) * contracts * cs
            buy_price, sell_price = entry_price, exit_price
        else:
            profit = (entry_price - exit_price) * contracts * cs
            buy_price, sell_price = exit_price, entry_price
        cost = entry_price * contracts * cs
        profit_pct = (profit / cost * 100) if cost > 0 else 0.0

        async with async_session() as session:
            session.add(Trade(
                strategy_id=None,
                symbol=symbol,
                buy_price=round(buy_price, 6),
                sell_price=round(sell_price, 6),
                quantity=contracts,
                profit=round(profit, 4),
                profit_pct=round(profit_pct, 4),
                sell_order_id=str(order.get("id") or "") if order else "",
                opened_at=_utcnow_naive(),
                closed_at=_utcnow_naive(),
            ))
            await session.commit()
        log.info(f"[MANUAL_TRADE_RECORDED] symbol={symbol} side={side} "
                 f"contracts={contracts} entry={entry_price:.6f} exit={exit_price:.6f} "
                 f"profit={profit:.4f}")
    except Exception as e:
        log.warning(f"record manual close failed (non-fatal): {e}")


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
    """获取当前合约持仓列表（v2.0 合约模式：多头/空头双向持仓）"""
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
    """市价平仓（v2.0 合约模式）：对指定交易对的合约持仓下达 reduce-only 市价单。

    自动判断持仓方向（多→卖、空→买），reduce-only 确保只平仓不开新仓。
    需 confirm=true 确认执行。
    """
    if not req.confirm:
        return {"success": False, "error": "需 confirm=true 确认平仓操作"}

    asset = req.asset.upper()

    # 从合约持仓中定位该交易对
    try:
        positions = await asyncio.to_thread(exmod.shared_exchange.fetch_positions)
    except Exception as e:
        log.error(f"ClosePosition: fetch_positions failed: {e}")
        return {"success": False, "error": f"获取持仓失败: {e}"}

    target = None
    for p in positions:
        if asset in (p.get("symbol") or ""):
            target = p
            break
    if target is None:
        return {"success": False, "error": f"无 {asset} 合约持仓"}

    symbol = target.get("symbol") or f"{asset}/USDT"
    side = target.get("side", "")
    contracts = float(target.get("contracts", 0) or 0)
    entry_price = float(target.get("entry_price", 0) or 0)
    mark_price = float(target.get("mark_price", 0) or 0)
    if contracts <= 0:
        return {"success": False, "error": f"无 {asset} 合约持仓"}

    # 平多→卖、平空→买，均 reduce-only
    close_side = "sell" if side == "long" else "buy"
    try:
        order = await asyncio.to_thread(
            exmod.shared_exchange.create_market_order, symbol, close_side, contracts, True
        )
    except Exception as e:
        log.error(f"ClosePosition: close failed for {symbol}: {e}")
        return {"success": False, "error": f"平仓失败: {e}"}

    # 成交均价：优先 order.price → 次选 cost/filled → 兜底 mark_price
    exit_price = float((order or {}).get("price") or 0)
    if exit_price <= 0 and order:
        filled = float(order.get("filled") or 0)
        cost = float(order.get("cost") or 0)
        if filled > 0 and cost > 0:
            exit_price = cost / filled
    if exit_price <= 0:
        exit_price = mark_price

    # V5 问题2：平仓落库 Trade，让仪表盘「最近成交」/绩效曲线反映真实成交
    await _record_manual_close(symbol, side, contracts, entry_price, exit_price, order)

    log.info(f"ClosePosition: {symbol} ({side}) x{contracts} contracts closed reduce-only, "
             f"order={order.get('id') if order else 'N/A'}")

    return {
        "success": True,
        "data": {
            "asset": asset,
            "symbol": symbol,
            "side": side,
            "contracts": contracts,
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
