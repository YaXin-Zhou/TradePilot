"""交易所连接状态 API"""
import asyncio
import logging
from fastapi import APIRouter
from core.exchange import ExchangeClient, ExchangeError, shared_exchange as _exchange
from core.redis import get_redis
from config import settings
import time

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/exchange", tags=["exchange"])

# Redis key for cross-worker exchange status sharing
_EXCHANGE_STATUS_KEY = "exchange:connected"
_EXCHANGE_STATUS_TTL = 10  # 10 秒过期，每轮询刷新一次


@router.get("/status")
async def exchange_status():
    """返回交易所连接状态，跨 worker 共享（Redis 缓存 10s）"""
    # 先读 Redis（跨 worker 共享）
    try:
        r = await get_redis()
        if r:
            cached = await r.get(_EXCHANGE_STATUS_KEY)
            if cached:
                return {"success": True, "data": {"connected": True, "exchange": settings.EXCHANGE_NAME,
                    "testnet": settings.EXCHANGE_TESTNET, "has_api_key": bool(settings.EXCHANGE_API_KEY),
                    "last_error": None, "latency_ms": None}}
    except Exception:
        pass

    # 本地未连接则尝试连接（线程池，不阻塞 event loop）
    if not _exchange._connected:
        try:
            await asyncio.to_thread(_exchange._ensure_markets)
        except Exception as e:
            logger.warning(f"Exchange auto-connect failed: {e}")

    connected = _exchange._connected

    # 连接成功则写入 Redis 广播给其他 worker
    if connected:
        try:
            r = await get_redis()
            if r:
                await r.setex(_EXCHANGE_STATUS_KEY, _EXCHANGE_STATUS_TTL, "1")
        except Exception:
            pass

    result = {
        "connected": connected,
        "exchange": settings.EXCHANGE_NAME,
        "testnet": settings.EXCHANGE_TESTNET,
        "has_api_key": bool(settings.EXCHANGE_API_KEY),
        "last_error": None,
        "latency_ms": None,
    }
    return {"success": True, "data": result}


@router.post("/test-connection")
async def test_connection(body: dict = {}):
    """测试 API 连接，返回详细诊断信息"""
    api_key = body.get("api_key", settings.EXCHANGE_API_KEY)
    secret = body.get("secret", settings.EXCHANGE_SECRET)
    passphrase = body.get("passphrase", settings.EXCHANGE_PASSPHRASE)
    testnet = body.get("testnet", settings.EXCHANGE_TESTNET)

    client = ExchangeClient(
        exchange_name=settings.EXCHANGE_NAME,
        api_key=api_key or "",
        secret=secret or "",
        passphrase=passphrase or "",
        testnet=testnet,
    )

    errors = []
    t0 = time.time()
    try:
        t = client.fetch_ticker(settings.DEFAULT_SYMBOL)
        latency = int((time.time() - t0) * 1000)
        return {
            "success": True,
            "data": {
                "connected": True,
                "latency_ms": latency,
                "price": t.get("last"),
                "exchange": settings.EXCHANGE_NAME,
                "testnet": testnet,
            },
        }
    except ExchangeError as e:
        errors.append(str(e))
    except Exception as e:
        errors.append(f"{type(e).__name__}: {str(e)}")

    return {
        "success": False,
        "error": errors[0] if errors else "Connection failed",
        "data": {
            "connected": False,
            "latency_ms": int((time.time() - t0) * 1000),
            "errors": errors,
        },
    }
