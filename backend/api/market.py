"""市场数据 API - 带模拟数据后备"""
from fastapi import APIRouter, Query
from core.exchange import shared_exchange as _exchange
from config import settings
import time, random, math

router = APIRouter(prefix="/api/market", tags=["market"])


def _mock_ticker(symbol="BTC/USDT"):
    base_price = 86500
    change = random.uniform(-2, 2)
    return {
        "symbol": symbol,
        "bid": base_price - random.uniform(5, 20),
        "ask": base_price + random.uniform(5, 20),
        "last": base_price + change,
        "high": base_price + random.uniform(200, 500),
        "low": base_price - random.uniform(200, 500),
        "volume": random.uniform(5000, 15000),
        "quote_volume": random.uniform(4e8, 1.2e9),
        "change_pct": round(change, 2),
        "timestamp": int(time.time() * 1000),
    }


def _mock_ohlcv(count=200):
    data = []
    price = 85000
    t = int(time.time() * 1000) - count * 3600000
    for i in range(count):
        change = random.uniform(-300, 300)
        vol = random.uniform(50, 200)
        data.append({
            "timestamp": t,
            "open": price,
            "high": price + abs(change) + random.uniform(10, 50),
            "low": price - abs(change) - random.uniform(10, 50),
            "close": price + change,
            "volume": vol,
            "symbol": "BTC/USDT",
        })
        price += change * 0.3
        price = max(price, 50000)
        price = min(price, 120000)
        t += 3600000
    return data


def _mock_orderbook(limit=20):
    base = 86500
    bids = [[base - i * 10, random.uniform(0.1, 2)] for i in range(limit)]
    asks = [[base + i * 10, random.uniform(0.1, 2)] for i in range(limit)]
    return {"bids": bids, "asks": asks, "timestamp": int(time.time() * 1000)}


@router.get("/ticker")
async def get_ticker(symbol: str = settings.DEFAULT_SYMBOL):
    try:
        ticker = _exchange.fetch_ticker(symbol)
        return {"success": True, "data": ticker}
    except Exception:
        return {"success": True, "data": _mock_ticker(symbol), "_mock": True}


@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str = settings.DEFAULT_SYMBOL,
    timeframe: str = Query("1h", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(200, ge=10, le=1000),
):
    try:
        df = _exchange.fetch_ohlcv(symbol, timeframe, limit)
        data = df.to_dict(orient="records")
        return {"success": True, "data": data}
    except Exception:
        return {"success": True, "data": _mock_ohlcv(limit), "_mock": True}


@router.get("/orderbook")
async def get_orderbook(
    symbol: str = settings.DEFAULT_SYMBOL,
    limit: int = Query(20, ge=5, le=50),
):
    try:
        ob = _exchange.fetch_orderbook(symbol, limit)
        return {"success": True, "data": ob}
    except Exception:
        return {"success": True, "data": _mock_orderbook(limit), "_mock": True}
