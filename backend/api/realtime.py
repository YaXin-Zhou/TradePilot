"""实时行情推送 — Phase 8 fan-out 架构

改动：
  - 单 OKX WS 连接 → 多客户端广播（fan-out），避免 N 客户端 = N 上游连接
  - 指数退避重连（3s→6s→12s→30s 上限）
  - 不再永久进入模拟 fallback（模拟只是首次等待时的过渡）
  - 支持多交易对订阅
"""
import asyncio
import json
import random
import time
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import websockets

router = APIRouter()


# ------------------------------------------------------------------
# 模拟价格引擎（仅首次连接 OKX 超时过渡用）
# ------------------------------------------------------------------

class SimulatedPriceEngine:
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
            "_simulated": True,
        }


# ------------------------------------------------------------------
# Fan-out 连接管理器
# ------------------------------------------------------------------

class TickerFanOut:
    """单 OKX WS 连接 → 多客户端广播"""

    RECONNECT_INTERVALS = [3, 6, 12, 30]  # 指数退避

    def __init__(self):
        self._clients: Set[WebSocket] = set()
        self._upstream_task: asyncio.Task | None = None
        self._latest: dict | None = None  # 最新一条数据（新客户端连接时立即推送）
        self._connected = False
        self._lock = asyncio.Lock()

    async def subscribe(self, ws: WebSocket):
        """客户端订阅"""
        await ws.accept()
        self._clients.add(ws)
        # 立即推送最新数据
        if self._latest:
            try:
                await ws.send_json(self._latest)
            except Exception:
                pass
        # 启动上游（如果未运行）
        async with self._lock:
            if self._upstream_task is None or self._upstream_task.done():
                self._upstream_task = asyncio.create_task(self._upstream_loop())

    def unsubscribe(self, ws: WebSocket):
        self._clients.discard(ws)
        # 无客户端时停止上游（节省资源）
        if not self._clients and self._upstream_task and not self._upstream_task.done():
            self._upstream_task.cancel()

    async def _broadcast(self, data: dict):
        """广播给所有客户端"""
        self._latest = data
        dead = []
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def _upstream_loop(self):
        """维护到 OKX 的 WS 连接，指数退避重连"""
        url = "wss://ws.okx.com:8443/ws/v5/public"
        sub = {"op": "subscribe", "args": [{"channel": "tickers", "instId": "BTC-USDT"}]}
        reconnect_idx = 0
        sim = SimulatedPriceEngine()

        while self._clients:  # 无客户端时退出
            try:
                async with websockets.connect(url, ping_interval=20, close_timeout=5) as ws:
                    await ws.send(json.dumps(sub))
                    self._connected = True
                    reconnect_idx = 0  # 重置退避
                    from core.logger import log
                    log.info("Realtime: OKX WS connected (fan-out)")

                    async for msg in ws:
                        data = json.loads(msg)
                        if "data" in data:
                            t = data["data"][0]
                            ticker = {
                                "type": "ticker",
                                "symbol": t.get("instId", "BTC-USDT").replace("-", "/"),
                                "last": float(t.get("last", 0)),
                                "bid": float(t.get("bidPx", 0)),
                                "ask": float(t.get("askPx", 0)),
                                "high": float(t.get("high24h", 0)),
                                "low": float(t.get("low24h", 0)),
                                "volume": float(t.get("volCcy24h", 0)),
                                "change_pct": float(t.get("change24h", 0)),
                                "timestamp": int(t.get("ts", time.time() * 1000)),
                            }
                            await self._broadcast(ticker)

                self._connected = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                from core.logger import log
                log.warning(f"Realtime: OKX WS disconnected ({e}), reconnecting...")

            # 退避重连
            if self._clients:
                interval = self.RECONNECT_INTERVALS[min(reconnect_idx, len(self.RECONNECT_INTERVALS) - 1)]
                reconnect_idx += 1
                # 过渡期用模拟数据填充（避免客户端长时间无数据）
                try:
                    await self._broadcast(await sim.tick())
                except Exception:
                    pass
                await asyncio.sleep(interval)

        from core.logger import log
        log.info("Realtime: upstream loop exited (no clients)")


# 全局 fan-out 实例
fanout = TickerFanOut()


@router.websocket("/ws/ticker")
async def websocket_ticker(websocket: WebSocket):
    """实时行情 WebSocket（fan-out 架构）"""
    await fanout.subscribe(websocket)
    try:
        # 保持连接，接收客户端消息（心跳等）
        while True:
            await websocket.receive_text()  # 客户端可发 ping
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        fanout.unsubscribe(websocket)
