"""v1.3 U6: 链上数据获取抽象层

支持 Glassnode / Coinglass API，不可用时优雅降级。
"""
import time
from typing import Optional
from core.logger import log

# 内存缓存（简单 TTL）
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 3600  # 1 小时


def _cached(key: str, ttl: int = CACHE_TTL):
    """简单的函数返回值缓存装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_key = f"{key}:{args}:{kwargs}"
            if cache_key in _cache:
                ts, val = _cache[cache_key]
                if time.time() - ts < ttl:
                    return val
            result = func(*args, **kwargs)
            _cache[cache_key] = (time.time(), result)
            return result
        return wrapper
    return decorator


@_cached("mvrv", ttl=86400)
def fetch_mvrv_zscore(symbol: str = "BTC") -> Optional[dict]:
    """获取 MVRV Z-Score（Glassnode API）

    降级：API Key 未配置时返回 None，调用方应跳过此信号。
    """
    try:
        import os
        api_key = os.getenv("GLASSNODE_API_KEY", "")
        if not api_key:
            log.debug("Glassnode API key not configured — skipping MVRV")
            return None
        # TODO: 真实 API 调用
        # import httpx
        # async with httpx.AsyncClient() as c:
        #     resp = await c.get(f"https://api.glassnode.com/v1/metrics/market/mvrv_z_score",
        #         params={"a": symbol, "api_key": api_key})
        return {"symbol": symbol, "mvrv_zscore": None, "source": "glassnode", "degraded": True}
    except Exception as e:
        log.warning(f"MVRV fetch failed: {e}")
        return None


@_cached("sopr", ttl=86400)
def fetch_sopr(symbol: str = "BTC") -> Optional[dict]:
    """获取 SOPR（Glassnode API）"""
    try:
        import os
        api_key = os.getenv("GLASSNODE_API_KEY", "")
        if not api_key:
            return None
        return {"symbol": symbol, "sopr": None, "source": "glassnode", "degraded": True}
    except Exception:
        return None


@_cached("netflow", ttl=3600)
def fetch_exchange_netflow(symbol: str = "BTC") -> Optional[dict]:
    """获取交易所净流入/流出（Coinglass API）"""
    try:
        return {"symbol": symbol, "netflow_24h": None, "source": "coinglass", "degraded": True}
    except Exception:
        return None


@_cached("active_addresses", ttl=86400)
def fetch_active_addresses(symbol: str = "BTC") -> Optional[dict]:
    """获取活跃地址数（Glassnode API）"""
    try:
        import os
        api_key = os.getenv("GLASSNODE_API_KEY", "")
        if not api_key:
            return None
        return {"symbol": symbol, "active_addresses": None, "source": "glassnode", "degraded": True}
    except Exception:
        return None
