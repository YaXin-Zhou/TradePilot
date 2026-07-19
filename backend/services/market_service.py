"""行情数据服务层"""
import time
import random
from core.exchange import shared_exchange
from core.logger import log


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


def get_ticker(symbol: str) -> tuple[dict, bool]:
    """获取行情。返回 (data, is_mock)"""
    try:
        ticker = shared_exchange.fetch_ticker(symbol)
        return ticker, False
    except Exception as e:
        log.warning(f"Ticker fetch failed for {symbol}: {e}")
        return _mock_ticker(symbol), True


def get_ohlcv(symbol: str, timeframe: str, limit: int) -> tuple[list, bool]:
    """获取 K 线。返回 (data, is_mock)"""
    try:
        df = shared_exchange.fetch_ohlcv(symbol, timeframe, limit)
        return df.to_dict(orient="records"), False
    except Exception as e:
        log.warning(f"OHLCV fetch failed for {symbol}: {e}")
        return _mock_ohlcv(limit), True


def get_orderbook(symbol: str, limit: int) -> tuple[dict, bool]:
    """获取订单簿。返回 (data, is_mock)"""
    try:
        ob = shared_exchange.fetch_orderbook(symbol, limit)
        return ob, False
    except Exception as e:
        log.warning(f"Orderbook fetch failed for {symbol}: {e}")
        return _mock_orderbook(limit), True
