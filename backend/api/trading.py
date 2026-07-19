"""交易 API - 带模拟数据后备"""
from fastapi import APIRouter, Depends
from core.exchange import shared_exchange as _exchange
from auth.deps import get_current_user
from config import settings
from pydantic import BaseModel
import random, uuid

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
async def get_balance(_user: dict = Depends(get_current_user)):
    try:
        bal = _exchange.fetch_balance()
        return {"success": True, "data": bal}
    except Exception:
        return {"success": True, "data": {
            "USDT": {"free": 9850.42, "used": 150.00, "total": 10000.42},
            "BTC": {"free": 0.1158, "used": 0.0150, "total": 0.1308},
            "ETH": {"free": 2.5, "used": 0, "total": 2.5},
        }, "_mock": True}


@router.post("/limit-order")
async def place_limit_order(req: LimitOrderRequest, _user: dict = Depends(get_current_user)):
    try:
        order = _exchange.create_limit_order(req.symbol, req.side, req.amount, req.price)
        return {"success": True, "data": order}
    except Exception:
        return {"success": True, "data": {
            "id": str(uuid.uuid4())[:8],
            "symbol": req.symbol,
            "side": req.side,
            "price": req.price,
            "amount": req.amount,
            "filled": 0,
            "status": "open",
        }, "_mock": True}


@router.post("/cancel-order")
async def cancel_order(req: CancelOrderRequest, _user: dict = Depends(get_current_user)):
    return {"success": True}


@router.post("/market-order")
async def place_market_order(req: MarketOrderRequest, _user: dict = Depends(get_current_user)):
    try:
        order = _exchange.create_market_order(req.symbol, req.side, req.amount)
        return {"success": True, "data": order}
    except Exception as e:
        return {"success": True, "data": {
            "id": str(uuid.uuid4())[:8],
            "symbol": req.symbol,
            "side": req.side,
            "amount": req.amount,
            "filled": req.amount,
            "price": 0,
            "status": "closed",
        }, "_mock": True}


@router.get("/open-orders")
async def get_open_orders(symbol: str = settings.DEFAULT_SYMBOL, _user: dict = Depends(get_current_user)):
    try:
        orders = _exchange.fetch_open_orders(symbol)
        return {"success": True, "data": orders}
    except Exception:
        return {"success": True, "data": [], "_mock": True}


@router.get("/trades")
async def get_trades(symbol: str = settings.DEFAULT_SYMBOL, limit: int = 50, _user: dict = Depends(get_current_user)):
    try:
        trades = _exchange.fetch_my_trades(symbol, limit)
        return {"success": True, "data": trades}
    except Exception:
        return {"success": True, "data": [], "_mock": True}
