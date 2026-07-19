"""市场数据 API"""
from fastapi import APIRouter, Query
from config import settings
from services.market_service import get_ticker, get_ohlcv, get_orderbook

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/ticker")
async def api_get_ticker(symbol: str = settings.DEFAULT_SYMBOL):
    data, is_mock = get_ticker(symbol)
    resp = {"success": True, "data": data}
    if is_mock:
        resp["_mock"] = True
    return resp


@router.get("/ohlcv")
async def api_get_ohlcv(
    symbol: str = settings.DEFAULT_SYMBOL,
    timeframe: str = Query("1h", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(200, ge=10, le=1000),
):
    data, is_mock = get_ohlcv(symbol, timeframe, limit)
    resp = {"success": True, "data": data}
    if is_mock:
        resp["_mock"] = True
    return resp


@router.get("/orderbook")
async def api_get_orderbook(
    symbol: str = settings.DEFAULT_SYMBOL,
    limit: int = Query(20, ge=5, le=50),
):
    data, is_mock = get_orderbook(symbol, limit)
    resp = {"success": True, "data": data}
    if is_mock:
        resp["_mock"] = True
    return resp
