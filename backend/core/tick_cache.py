"""TTL Tick 缓存 — 消除单 tick 内重复 REST 调用

M2 核心基础设施：同一 symbol 在 TTL 窗口内只发出 1 次网络请求。

典型场景：
  - trading_service._get_price() 和 runner tick 循环同时请求 BTC/USDT
  - 改造前：各自调用 fetch_ticker → 2 次 REST
  - 改造后：第一次调用缓存，第二次命中 → 1 次 REST
"""
import asyncio
import time
from typing import Optional


class TickCache:
    """TTL 内存缓存，key = (exchange_name, symbol)"""

    def __init__(self, ttl_seconds: float = 0.5):
        self._ttl = ttl_seconds
        # key -> (fetch_timestamp, ticker_dict, error)
        self._cache: dict[str, tuple[float, Optional[dict], Optional[Exception]]] = {}
        # 防止缓存击穿：正在获取的 key 的锁
        self._locks: dict[str, asyncio.Lock] = {}

    def _key(self, exchange_name: str, symbol: str) -> str:
        return f"{exchange_name}:{symbol}"

    async def get(self, exchange, symbol: str) -> dict:
        """获取 ticker。缓存未过期直接返回；否则 await fetch_ticker 并存入。

        Args:
            exchange: ExchangeClient 实例（有 fetch_ticker 同步方法）
            symbol: 交易对，如 "BTC/USDT"

        Returns:
            ticker dict（与 ExchangeClient.fetch_ticker 返回格式一致）
        """
        key = self._key(exchange.name, symbol)
        now = time.time()

        # 1. 检查缓存是否命中
        if key in self._cache:
            ts, ticker, err = self._cache[key]
            if now - ts < self._ttl:
                if err:
                    raise err  # 缓存了错误也重放（防止错误风暴）
                return ticker

        # 2. 防击穿：同一 key 并发只发一个请求
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        async with self._locks[key]:
            # double-check（持锁后可能已被其他协程填充）
            if key in self._cache:
                ts, ticker, err = self._cache[key]
                if now - ts < self._ttl:
                    if err:
                        raise err
                    return ticker

            # 3. 实际获取
            try:
                ticker = await asyncio.to_thread(exchange.fetch_ticker, symbol)
                self._cache[key] = (time.time(), ticker, None)
                return ticker
            except Exception as e:
                # 缓存错误 0.5s，防止错误风暴（但 TTL 更短）
                self._cache[key] = (time.time(), None, e)
                raise

    def invalidate(self, symbol: str = None, exchange_name: str = None):
        """清除缓存。不传参数则清空全部。"""
        if not symbol and not exchange_name:
            self._cache.clear()
            return
        keys_to_del = []
        for k in self._cache:
            parts = k.split(":", 1)
            ex_name, sym = parts[0], parts[1] if len(parts) > 1 else ""
            if symbol and sym != symbol:
                continue
            if exchange_name and ex_name != exchange_name:
                continue
            keys_to_del.append(k)
        for k in keys_to_del:
            del self._cache[k]

    def stats(self) -> dict:
        """返回缓存统计（调试用）"""
        return {"entries": len(self._cache), "ttl_seconds": self._ttl}


# 模块级单例
tick_cache = TickCache(ttl_seconds=0.5)
