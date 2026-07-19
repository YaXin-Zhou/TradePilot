"""实时行情推送 - OKX WebSocket + 模拟降级"""
import asyncio
import json
import os
import random
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import websockets

router = APIRouter()


class SimulatedPriceEngine:
    """Fallback when real WebSocket is unavailable"""
    def __init__(self, base_price: float = 86500.0):
        self.price = base_price

    async def tick(self) -> dict:
        step = random.gauss(0, 20)
        self.price += step
        self.price = max(50000, min(120000, self.price))
        spread = random.uniform(1, 15)
        return {
            "type": "ticker", "symbol": "BTC/USDT",
            "last": round(self.price, 2),
            "bid": round(self.price - spread / 2, 2),
            "ask": round(self.price + spread / 2, 2),
            "volume": round(random.uniform(100, 500), 2),
            "timestamp": int(time.time() * 1000),
        }


async def _okx_ws_ticker(symbol: str = "BTC-USDT"):
    """Connect to OKX WebSocket and yield ticker data (auto-reconnect on error)"""
    url = "wss://ws.okx.com:8443/ws/v5/public"
    sub = {"op": "subscribe", "args": [{"channel": "tickers", "instId": symbol}]}
    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                async for msg in ws:
                    data = json.loads(msg)
                    if "data" in data:
                        t = data["data"][0]
                        yield {
                            "type": "ticker",
                            "symbol": t.get("instId", symbol).replace("-", "/"),
                            "last": float(t.get("last", 0)),
                            "bid": float(t.get("bidPx", 0)),
                            "ask": float(t.get("askPx", 0)),
                            "high": float(t.get("high24h", 0)),
                            "low": float(t.get("low24h", 0)),
                            "volume": float(t.get("volCcy24h", 0)),
                            "change_pct": float(t.get("change24h", 0)),
                            "timestamp": int(t.get("ts", time.time() * 1000)),
                        }
        except Exception:
            await asyncio.sleep(3)


@router.websocket("/ws/ticker")
async def websocket_ticker(websocket: WebSocket):
    await websocket.accept()
    sim = SimulatedPriceEngine()
    gen = _okx_ws_ticker()
    try:
        try:
            first = await asyncio.wait_for(gen.__anext__(), timeout=10)
            await websocket.send_json(first)
            async for data in gen:
                await websocket.send_json(data)
        except (asyncio.TimeoutError, Exception):
            while True:
                await websocket.send_json(await sim.tick())
                await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass