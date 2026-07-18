"""交易所连接状态 API"""
from fastapi import APIRouter
from core.exchange import ExchangeClient, _connected, ExchangeError, shared_exchange as _exchange
from config import settings
import time

router = APIRouter(prefix="/api/exchange", tags=["exchange"])


@router.get("/status")
async def exchange_status():
    """返回交易所连接状态和最近错误"""
    result = {
        "connected": _connected,
        "exchange": settings.EXCHANGE_NAME,
        "testnet": settings.EXCHANGE_TESTNET,
        "has_api_key": bool(settings.EXCHANGE_API_KEY),
        "last_error": None,
        "latency_ms": None,
    }
    if _connected:
        try:
            t0 = time.time()
            t = _exchange.fetch_ticker(settings.DEFAULT_SYMBOL)
            result["latency_ms"] = int((time.time() - t0) * 1000)
            result["last_price"] = t.get("last")
        except Exception as e:
            result["connected"] = False
            result["last_error"] = str(e)
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
