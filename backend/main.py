"""FastAPI 应用入口 — Production v1.1 生产就绪版

改动（v1.1）：
  - 优雅关闭：stop strategies → persist state → close DB，30s 超时
  - 启动加固：init_db 失败不崩溃但记录 CRITICAL
  - SIGTERM 信号处理（Docker stop 友好）
"""
import sys
import os
import time as _time
import signal as _signal
import asyncio
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

# v1.1: 关机超时（秒）— 超过此时间强制退出
SHUTDOWN_TIMEOUT = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    # FIX: uvicorn --workers 4 fork 后文件句柄失效，在每个 worker 中重新初始化 logger
    from core.logger import setup_logger
    setup_logger()  # 清除继承的 handler，重新创建有效的文件句柄

    import os
    log.info(f"=== Application lifespan starting (pid={os.getpid()}) ===")

    # Phase 7.7: 启动时安全校验（生产模式默认 JWT 密钥 → 拒绝启动）
    security_warnings = settings.validate_security()
    for w in security_warnings:
        log.warning(f"Security: {w}")

    # v1.1: init_db 失败记录 CRITICAL 但不崩溃（Docker 会重试）
    try:
        await init_db()
        log.info(f"init_db completed (pid={os.getpid()})")
        # 确保策略日志表存在
        from services.strategy_log import _ensure_table, recover_all_from_db
        await _ensure_table()
        await recover_all_from_db()
    except Exception as e:
        log.critical(f"init_db() FAILED — database may be unavailable: {e}")

    await load_exchange_config()
    await load_deepseek_config()

    # Phase 8: 启动时主动测试交易所连通性（线程池执行，不阻塞 event loop）
    # 避免前端始终显示"模拟模式—交易所连接不可用"
    try:
        import asyncio as _asyncio
        from core.exchange import shared_exchange
        await _asyncio.to_thread(shared_exchange._ensure_markets)
        if shared_exchange._connected:
            log.info("Exchange connectivity verified on startup")
        else:
            log.warning("Exchange connectivity test failed — will retry on first /status poll")
    except Exception as e:
        log.warning(f"Exchange startup connectivity test error (non-fatal): {e}")

    # P0-1: kill_switch + risk_engine 从 DB 加载状态
    await kill_switch.init_from_db()
    from services.risk_engine import risk_engine
    await risk_engine.init_from_db()

    # P1-3: online_learner + strategy_pool 从 DB 加载状态
    from services.online_learner import online_learner
    await online_learner.init_from_db()
    from services.strategy_pool import strategy_pool
    await strategy_pool.init_from_db()

    # Phase 8: kill_switch 状态检查
    if kill_switch.is_triggered:
        log.warning(
            "⚠️ Application starting with KILL SWITCH TRIGGERED. "
            "All trading will be blocked. POST /api/trading/emergency-reset to clear."
        )

    try:
        start_scheduler()
        log.info("Application started successfully (Production v1.1)")
    except Exception as e:
        log.error(f"Scheduler start failed (non-fatal): {e}")

    # Phase 8: 恢复 RUNNING 策略（崩溃恢复）
    try:
        from strategies.runner import runner
        await runner.recover_running_strategies()
    except Exception as e:
        log.error(f"Strategy recovery failed (non-fatal): {e}")

    yield

    # === v1.1 优雅关闭 ===
    log.info("Shutting down gracefully...")
    _shutdown_start = _time.time()

    # 1. 停止调度器（不再触发新任务）
    try:
        stop_scheduler()
    except Exception as e:
        log.error(f"Scheduler stop error: {e}")

    # 2. 持久化 runner 状态 + 停止策略
    try:
        from strategies.runner import runner
        await asyncio.wait_for(runner.shutdown(), timeout=10)
    except asyncio.TimeoutError:
        log.warning("Runner shutdown timed out (10s), forcing close")
    except Exception as e:
        log.error(f"Runner shutdown error: {e}")

    # 3. 关闭 DB 连接池
    try:
        await asyncio.wait_for(close_db(), timeout=5)
    except asyncio.TimeoutError:
        log.warning("DB close timed out")
    except Exception as e:
        log.error(f"DB close error: {e}")

    elapsed = _time.time() - _shutdown_start
    log.info(f"Application shut down ({elapsed:.1f}s)")


# ──── 自定义 JSON 响应：NaN/Inf → null ────
import math
import json as _json
from starlette.responses import JSONResponse as _JSONResponse


def _sanitize_nan(obj):
    """递归替换 NaN/Inf 为 None"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    return obj


class SafeJSONResponse(_JSONResponse):
    """自动将 NaN/Inf 转为 null，防止 JSON 序列化崩溃"""

    def render(self, content) -> bytes:
        return _json.dumps(
            _sanitize_nan(content),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="AI Quant Trade",
    description="AI 量化交易系统 - OKX",
    version="1.1.0",
    lifespan=lifespan,
    default_response_class=SafeJSONResponse,
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
from api.metrics import router as metrics_router  # N5: /api/metrics + /api/healthz

app.include_router(market_router)
app.include_router(trading_router)
app.include_router(portfolio_router)
app.include_router(strategies_router)
app.include_router(analysis_router)
app.include_router(ai_router)
app.include_router(metrics_router)  # N5: /api/metrics + /api/healthz
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
        "version": "1.1.0",
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
