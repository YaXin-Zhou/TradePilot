"""交易 API"""
from fastapi import APIRouter, Depends
from auth.deps import get_current_user
from config import settings
from pydantic import BaseModel
from services.trading_service import (
    get_balance, place_limit_order, place_market_order,
    get_open_orders, get_trade_history,
)

router = APIRouter(prefix="/api/trading", tags=["trading"])


class LimitOrderRequest(BaseModel):
    symbol: str = settings.DEFAULT_SYMBOL
    side: str
    amount: float
    price: float


class CancelOrderRequest(BaseModel):
    symbol: str = settings.DEFAULT_SYMBOL
    order_id: str


class MarketOrderRequest(BaseModel):
    symbol: str = settings.DEFAULT_SYMBOL
    side: str
    amount: float


@router.get("/balance")
async def api_get_balance(_user: dict = Depends(get_current_user)):
    data, is_mock = await get_balance()
    resp = {"success": True, "data": data}
    if is_mock:
        resp["_mock"] = True
    return resp


@router.post("/limit-order")
async def api_limit_order(req: LimitOrderRequest, _user: dict = Depends(get_current_user)):
    order, error, is_mock = await place_limit_order(
        _user.get("id", "system"), req.symbol, req.side, req.amount, req.price
    )
    if error:
        return {"success": False, "error": error}
    resp = {"success": True, "data": order}
    if is_mock:
        resp["_mock"] = True
    return resp


@router.post("/cancel-order")
async def api_cancel_order(req: CancelOrderRequest, _user: dict = Depends(get_current_user)):
    return {"success": True}


@router.post("/market-order")
async def api_market_order(req: MarketOrderRequest, _user: dict = Depends(get_current_user)):
    order, error, is_mock = await place_market_order(
        _user.get("id", "system"), req.symbol, req.side, req.amount
    )
    if error:
        return {"success": False, "error": error}
    resp = {"success": True, "data": order}
    if is_mock:
        resp["_mock"] = True
    return resp


@router.get("/open-orders")
async def api_open_orders(symbol: str = settings.DEFAULT_SYMBOL, _user: dict = Depends(get_current_user)):
    data, is_mock = get_open_orders(symbol)
    resp = {"success": True, "data": data}
    if is_mock:
        resp["_mock"] = True
    return resp


@router.get("/trades")
async def api_trades(symbol: str = settings.DEFAULT_SYMBOL, limit: int = 50, _user: dict = Depends(get_current_user)):
    data, is_mock = get_trade_history(symbol, limit)
    resp = {"success": True, "data": data}
    if is_mock:
        resp["_mock"] = True
    return resp
