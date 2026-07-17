"""实时行情推送 - WebSocket 端点"""
import asyncio
import random
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class SimulatedPriceEngine:
    def __init__(self, base_price: float = 86500.0):
        self.price = base_price
        self.bid = base_price - random.uniform(2, 8)
        self.ask = base_price + random.uniform(2, 8)
        self.high = base_price
        self.low = base_price
        self.volume = 0
        self.change_pct = 0.0
        self.open_price = base_price

    async def tick(self) -> dict:
        step = random.gauss(0, 20)
        self.price += step
        self.price = max(50000, min(120000, self.price))
        self.high = max(self.high, self.price)
        self.low = min(self.low, self.price)
        spread = random.uniform(1, 15)
        self.bid = self.price - spread / 2
        self.ask = self.price + spread / 2
        self.volume += random.uniform(0.5, 5)
        self.change_pct = (self.price - self.open_price) / self.open_price * 100
        now = int(time.time() * 1000)
        return {
            "type": "ticker",
            "symbol": "BTC/USDT",
            "last": round(self.price, 2),
            "bid": round(self.bid, 2),
            "ask": round(self.ask, 2),
            "high": round(self.high, 2),
            "low": round(self.low, 2),
            "volume": round(self.volume, 2),
            "change_pct": round(self.change_pct, 2),
            "timestamp": now,
        }

    def reset_hour(self):
        self.open_price = self.price
        self.high = self.price
        self.low = self.price
        self.volume = 0


_price_engine = SimulatedPriceEngine()


@router.websocket("/ws/ticker")
async def websocket_ticker(websocket: WebSocket):
    await websocket.accept()
    engine = _price_engine
    last_hour_reset = time.time()
    try:
        while True:
            now = time.time()
            if now - last_hour_reset > 3600:
                engine.reset_hour()
                last_hour_reset = now
            ticker_data = await engine.tick()
            await websocket.send_json(ticker_data)
            await websocket.send_json({
                "type": "candle",
                "symbol": "BTC/USDT",
                "timestamp": int(now * 1000),
                "open": round(engine.open_price, 2),
                "high": round(engine.high, 2),
                "low": round(engine.low, 2),
                "close": round(engine.price, 2),
                "volume": round(engine.volume, 4),
            })
            await asyncio.sleep(2)
    except (WebSocketDisconnect, Exception):
        pass
