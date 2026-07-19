"""FastAPI 应用入口 — Phase 8 实盘就绪版

改动：
  - lifespan 中恢复 RUNNING 策略（崩溃恢复）
  - /api/health 增加 DB + 交易所连通性检查
  - /api/health/deep 深度健康检查
  - kill_switch 状态在 health 中暴露
"""
import sys
import os
import time as _time
from contextlib import asynccontextmanager

# 确保 backend 在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from db.database import init_db, close_db, async_session
from tasks.scheduler import start_scheduler, stop_scheduler
from load_db_config import load_exchange_config, load_deepseek_config
from core.rate_limiter import rate_limit_middleware
from core.errors import global_error_handler, sanitize_exception_handler
from core.logger import log
from core.kill_switch import kill_switch


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 7.7: 启动时安全校验（生产模式默认 JWT 密钥 → 拒绝启动）
    security_warnings = settings.validate_security()
    for w in security_warnings:
        log.warning(f"Security: {w}")

    await init_db()
    await load_exchange_config()
    await load_deepseek_config()

    # P0-1: kill_switch + risk_engine 从 DB 加载状态（替代 JSON 文件）
    await kill_switch.init_from_db()
    from services.risk_engine import risk_engine
    await risk_engine.init_from_db()

    # Phase 8: kill_switch 状态检查
    if kill_switch.is_triggered:
        log.warning(
            "⚠️ Application starting with KILL SWITCH TRIGGERED. "
            "All trading will be blocked. POST /api/trading/emergency-reset to clear."
        )

    try:
        start_scheduler()
        log.info("Application started successfully")
    except Exception as e:
        log.error(f"Scheduler start failed (non-fatal): {e}")

    # Phase 8: 恢复 RUNNING 策略（崩溃恢复）
    try:
        from strategies.runner import runner
        await runner.recover_running_strategies()
    except Exception as e:
        log.error(f"Strategy recovery failed (non-fatal): {e}")

    yield

    stop_scheduler()
    await close_db()
    log.info("Application shut down")


app = FastAPI(
    title="AI Quant Trade",
    description="AI 量化交易系统 - OKX",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — 白名单模式，仅允许配置的域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 速率限制中间件
app.middleware("http")(rate_limit_middleware)

# 全局错误处理中间件
app.middleware("http")(global_error_handler)

# 兜底异常处理器
app.add_exception_handler(Exception, sanitize_exception_handler)

# 注册路由
from api.market import router as market_router
from api.trading import router as trading_router
from api.portfolio import router as portfolio_router
from api.strategies import router as strategies_router
from api.analysis import router as analysis_router
from api.ai_strategy import router as ai_router

app.include_router(market_router)
app.include_router(trading_router)
app.include_router(portfolio_router)
app.include_router(strategies_router)
app.include_router(analysis_router)
app.include_router(ai_router)
from auth.router import router as auth_router
app.include_router(auth_router)


@app.get("/api/health")
async def health():
    """基础健康检查（轻量，不查 DB/交易所）"""
    return {
        "status": "ok",
        "exchange": settings.EXCHANGE_NAME,
        "testnet": settings.EXCHANGE_TESTNET,
        "kill_switch": kill_switch.get_state()["status"],
        "version": "0.2.0",
    }


@app.get("/api/health/deep")
async def health_deep():
    """深度健康检查 — DB + 交易所连通性 + 延迟

    Phase 8: 用于监控系统和判断是否真正可用。
    """
    result = {
        "status": "ok",
        "timestamp": _time.time(),
        "checks": {},
        "exchange": settings.EXCHANGE_NAME,
        "testnet": settings.EXCHANGE_TESTNET,
        "kill_switch": kill_switch.get_state()["status"],
        "mode": "TESTNET" if settings.EXCHANGE_TESTNET else "LIVE",
    }

    # 1. DB 检查
    try:
        from sqlalchemy import text
        async with async_session() as session:
            start = _time.time()
            await session.execute(text("SELECT 1"))
            db_latency = int((_time.time() - start) * 1000)
        result["checks"]["database"] = {"ok": True, "latency_ms": db_latency}
    except Exception as e:
        result["checks"]["database"] = {"ok": False, "error": str(e)}
        result["status"] = "degraded"

    # 2. 交易所连通性
    try:
        from core.exchange import shared_exchange
        start = _time.time()
        ok, msg, latency = shared_exchange.test_connection()
        result["checks"]["exchange"] = {
            "ok": ok,
            "message": msg,
            "latency_ms": latency,
            "testnet": shared_exchange.is_testnet,
        }
        if not ok:
            result["status"] = "degraded"
    except Exception as e:
        result["checks"]["exchange"] = {"ok": False, "error": str(e)}
        result["status"] = "degraded"

    # 3. 运行中策略数
    try:
        from strategies.runner import runner
        result["checks"]["strategies"] = {
            "running": len(runner._tasks),
            "positions": len(runner._positions_usdt),
        }
    except Exception:
        result["checks"]["strategies"] = {"running": 0}

    # 4. 风控参数
    result["checks"]["risk_limits"] = {
        "max_order_amount_usdt": settings.MAX_ORDER_AMOUNT_USDT,
        "max_total_position_usdt": settings.MAX_TOTAL_POSITION_USDT,
        "live_whitelist": settings.LIVE_SYMBOL_WHITELIST,
    }

    return result


from api.realtime import router as realtime_router
from api.backtest import router as backtest_router
from api.exchange import router as exchange_router

app.include_router(realtime_router)
app.include_router(backtest_router)
# settings_router 已在上方注册（api.settings）— 避免重复
# 但原代码用 settings_router 变量名，这里重新引入以保持兼容
try:
    from api.settings import router as settings_router
    app.include_router(settings_router)
except ImportError:
    pass
app.include_router(exchange_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
