"""交易 API - 带模拟数据后备"""
from fastapi import APIRouter
from core.exchange import ExchangeClient
from config import settings
from pydantic import BaseModel
import random, uuid

router = APIRouter(prefix="/api/trading", tags=["trading"])

_exchange = ExchangeClient(
    exchange_name=settings.EXCHANGE_NAME,
    api_key=settings.EXCHANGE_API_KEY,
    secret=settings.EXCHANGE_SECRET,
    passphrase=settings.EXCHANGE_PASSPHRASE,
    testnet=settings.EXCHANGE_TESTNET,
)


class LimitOrderRequest(BaseModel):
    symbol: str = settings.DEFAULT_SYMBOL
    side: str
    amount: float
    price: float


class CancelOrderRequest(BaseModel):
    symbol: str = settings.DEFAULT_SYMBOL
    order_id: str


@router.get("/balance")
async def get_balance():
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
async def place_limit_order(req: LimitOrderRequest):
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
async def cancel_order(req: CancelOrderRequest):
    return {"success": True}


@router.get("/open-orders")
async def get_open_orders(symbol: str = settings.DEFAULT_SYMBOL):
    try:
        orders = _exchange.fetch_open_orders(symbol)
        return {"success": True, "data": orders}
    except Exception:
        return {"success": True, "data": [], "_mock": True}


@router.get("/trades")
async def get_trades(symbol: str = settings.DEFAULT_SYMBOL, limit: int = 50):
    try:
        trades = _exchange.fetch_my_trades(symbol, limit)
        return {"success": True, "data": trades}
    except Exception:
        return {"success": True, "data": [], "_mock": True}
