"""交易所连接状态 API"""
import asyncio
import logging
from fastapi import APIRouter, Depends
from core.exchange import ExchangeClient, ExchangeError
import core.exchange as exmod
from core.redis import get_redis
from config import settings
from auth.deps import require_admin
import time

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/exchange", tags=["exchange"])

# Redis key for cross-worker exchange status sharing
_EXCHANGE_STATUS_KEY = "exchange:connected"
_EXCHANGE_STATUS_TTL = 10  # 10 秒过期，每轮询刷新一次


def _get_exchange():
    """动态获取 shared_exchange 实例（避免热重建后引用过期）"""
    return exmod.shared_exchange


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

    # 动态获取最新实例（可能在 settings API 中被热重建过）
    _exchange = _get_exchange()

    # 本地未连接则尝试实际探测（不依赖 _connected 标志位）
    # FIX: 直接调用 ccxt 原始 fetch_ticker，绕过 ExchangeClient._try_reconnect()
    # 的退避守卫。否则退避期内（1s~60s）探测会直接被拦截，导致 /status
    # 永远返回 offline，即使网络已恢复。
    connected = _exchange.is_connected
    latency_ms = None
    if not connected:
        try:
            t0 = time.time()
            await asyncio.to_thread(_exchange._exchange.fetch_ticker, settings.DEFAULT_SYMBOL)
            latency_ms = int((time.time() - t0) * 1000)
            connected = True
            # 探测成功，更新标志位
            _exchange._mark_success()
            logger.info(f"Exchange status probe OK ({latency_ms}ms)")
        except Exception as e:
            logger.warning(f"Exchange status probe failed: {e}")

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
        "latency_ms": latency_ms,
    }
    return {"success": True, "data": result}


@router.post("/test-connection")
async def test_connection(body: dict = {}, _user: dict = Depends(require_admin)):
    """测试 API 连接，返回详细诊断信息（v2.0: 仅管理员）"""
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
