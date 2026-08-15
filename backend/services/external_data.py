"""
外部数据获取器 — OKX Open Interest + Fear & Greed Index

数据源:
  1. OKX Open Interest: 通过 CCXT 获取持仓量 / 多空比
  2. Fear & Greed Index: alternative.me API
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
import numpy as np

from core.logger import log
from services.feature_engine import OpenInterestData, FearGreedData


# ------------------------------------------------------------------
# OKX Open Interest Fetcher
# ------------------------------------------------------------------


@dataclass
class OIFetcher:
    """OKX 持仓数据获取器"""

    CACHE_TTL: float = 300.0  # 5分钟

    _cache: dict[str, tuple[float, OpenInterestData]] = field(default_factory=dict)

    async def fetch(self, symbol: str = "BTC/USDT") -> Optional[OpenInterestData]:
        """获取 OKX 持仓数据"""
        cache_key = symbol
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached[0] < self.CACHE_TTL:
            return cached[1]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1) 获取 Open Interest
                oi_result = await self._fetch_open_interest(client, symbol)

                # 2) 获取多空比（真实 OKX rubik 接口）
                ls_ratio, ls_change = await self._fetch_long_short_ratio(client, symbol)

                # 3) v2.1: 资金费率 + 期货基差
                funding_rate = await self._fetch_funding_rate(client, symbol)
                basis_pct = await self._fetch_futures_basis(client, symbol)

                if oi_result is None:
                    return None

                data = OpenInterestData(
                    symbol=symbol,
                    oi_contracts=oi_result.get("contracts", 0),
                    oi_usd=oi_result.get("usd_value", 0),
                    oi_change_1h_pct=oi_result.get("change_1h_pct", 0),
                    oi_change_24h_pct=oi_result.get("change_24h_pct", 0),
                    long_short_ratio=ls_ratio,
                    ls_ratio_change_pct=ls_change,
                    funding_rate=funding_rate,
                    futures_basis_pct=basis_pct,
                )

                self._cache[cache_key] = (time.time(), data)
                return data

        except Exception as e:
            log.warning(f"OIFetcher: failed for {symbol}: {e}")
            return None

    async def _fetch_open_interest(self, client: httpx.AsyncClient, symbol: str) -> Optional[dict]:
        """从 OKX API 获取持仓数据"""
        try:
            # OKX v5 API: /api/v5/public/open-interest
            inst_id = symbol.replace("/", "-") + "-SWAP"
            url = f"https://www.okx.com/api/v5/public/open-interest?instId={inst_id}"
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.json()

            if body.get("code") == "0" and body.get("data"):
                items = body["data"]
                current = items[0]
                oi_contracts = float(current.get("oi", 0))
                oi_usd = float(current.get("oiCcy", 0)) if current.get("oiCcy") else oi_contracts * 60000

                # 模拟 1h/24h 变化（OKX 不直接提供，需要历史数据）
                # 这里使用缓存中的历史值计算
                cache_key = f"_oi_history_{symbol}"
                now = time.time()
                history = self._cache.get(cache_key, (now, oi_contracts))
                _, prev_oi = history

                change_1h = ((oi_contracts - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0
                change_24h = change_1h  # 简化，实际应存储 24h 历史

                self._cache[cache_key] = (now, oi_contracts)

                return {
                    "contracts": oi_contracts,
                    "usd_value": oi_usd,
                    "change_1h_pct": change_1h,
                    "change_24h_pct": change_24h,
                }
        except Exception as e:
            log.debug(f"OIFetcher: OKX API error: {e}")

        return None

    async def _fetch_long_short_ratio(self, client: httpx.AsyncClient, symbol: str) -> tuple[float, float]:
        """获取多空比（OKX rubik 公开接口）"""
        try:
            ccy = symbol.split("/")[0]
            url = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={ccy}&period=5m"
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") == "0" and body.get("data"):
                rows = body["data"]
                # data 格式: [[ts, ratio], [ts, ratio], ...]，ratio 为字符串
                cur = float(rows[0][1]) if len(rows) > 0 and len(rows[0]) > 1 else 1.0
                prev = float(rows[1][1]) if len(rows) > 1 and len(rows[1]) > 1 else cur
                change = ((cur - prev) / prev * 100) if prev > 0 else 0.0
                return cur, change
        except Exception as e:
            log.debug(f"OIFetcher: long/short ratio error: {e}")
        return 1.0, 0.0

    async def _fetch_funding_rate(self, client: httpx.AsyncClient, symbol: str) -> float:
        """获取当前资金费率（OKX 永续）"""
        try:
            inst_id = symbol.replace("/", "-") + "-SWAP"
            url = f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}"
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") == "0" and body.get("data"):
                return float(body["data"][0].get("fundingRate", 0) or 0)
        except Exception as e:
            log.debug(f"OIFetcher: funding rate error: {e}")
        return 0.0

    async def _fetch_futures_basis(self, client: httpx.AsyncClient, symbol: str) -> float:
        """获取期货基差 %（swap 标记价 vs 现货最新价）"""
        try:
            base, _, quote = symbol.partition("/")
            spot_id = f"{base}-{quote}"
            swap_id = f"{base}-{quote}-SWAP"
            # 现货最新价
            spot_resp = await client.get(f"https://www.okx.com/api/v5/market/ticker?instId={spot_id}")
            spot_resp.raise_for_status()
            spot_body = spot_resp.json()
            spot_price = float(spot_body["data"][0]["last"]) if spot_body.get("data") else 0.0
            # 合约标记价
            mark_resp = await client.get(f"https://www.okx.com/api/v5/public/mark-price?instId={swap_id}")
            mark_resp.raise_for_status()
            mark_body = mark_resp.json()
            mark_price = float(mark_body["data"][0]["markPx"]) if mark_body.get("data") else 0.0
            if spot_price > 0:
                return (mark_price - spot_price) / spot_price * 100
        except Exception as e:
            log.debug(f"OIFetcher: futures basis error: {e}")
        return 0.0

    def clear_cache(self):
        self._cache.clear()


oi_fetcher = OIFetcher()


# ------------------------------------------------------------------
# Fear & Greed Index Fetcher
# ------------------------------------------------------------------


@dataclass
class FearGreedFetcher:
    """恐惧贪婪指数获取器 (alternative.me)"""

    CACHE_TTL: float = 3600.0  # 1小时

    _cache: tuple[float, FearGreedData] | None = None
    _history: list[int] = field(default_factory=list)  # 30天历史

    async def fetch(self) -> Optional[FearGreedData]:
        """获取恐惧贪婪指数"""
        if self._cache and time.time() - self._cache[0] < self.CACHE_TTL:
            return self._cache[1]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 当天数据
                url = "https://api.alternative.me/fng/?limit=30"
                resp = await client.get(url)
                resp.raise_for_status()
                body = resp.json()

                if body.get("data"):
                    entries = body["data"]
                    current = entries[0]
                    value = int(current["value"])
                    classification = FearGreedData.classify(value)

                    # 日变化
                    prev_value = int(entries[1]["value"]) if len(entries) > 1 else value
                    change_1d = value - prev_value

                    # 历史值
                    self._history = [int(e["value"]) for e in entries]

                    # 30日分位数
                    percentile = sum(1 for v in self._history if v <= value) / max(len(self._history), 1)

                    data = FearGreedData(
                        value=value,
                        classification=classification,
                        value_change_1d=change_1d,
                        percentile_30d=round(percentile, 4),
                    )

                    self._cache = (time.time(), data)
                    log.info(f"FearGreedFetcher: value={value} ({classification}), 30d percentile={percentile:.2f}")
                    return data

        except Exception as e:
            log.warning(f"FearGreedFetcher: API error: {e}")

        return None

    def clear_cache(self):
        self._cache = None


fear_greed_fetcher = FearGreedFetcher()
