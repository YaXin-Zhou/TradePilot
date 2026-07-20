"""N5 + v1.2: 运行指标端点 + 详细健康检查 + Prometheus 导出

/api/metrics            — JSON 运行指标
/api/metrics/prometheus — Prometheus scrape endpoint
/api/healthz            — 标准命名健康检查（DB/Redis/Exchange 探测）
"""
import time as _time
from fastapi import APIRouter, Response

from config import settings
from db.database import async_session
from core.kill_switch import kill_switch
from core.logger import log

router = APIRouter(tags=["monitoring"])


# 应用启动时间（用于计算 uptime）
_APP_START_TIME = _time.time()


@router.get("/api/metrics")
async def get_metrics():
    """运行指标 — JSON 格式，可被 Prometheus exporter 或直接监控使用

    返回字段说明：
      uptime_seconds          — 应用运行时长（秒）
      kill_switch_active      — 紧急停止是否激活
      pending_order_records   — 订单补偿队列长度（>0 表示有 DB 写入失败待补偿）
      persist_fail_count      — 各策略连续持久化失败次数（≥3 需告警）
      active_strategies        — 运行中策略数
      recent_errors            — 最近 5 分钟错误数（best effort）
      tick_cache_size          — tick 缓存条目数
      version                  — 应用版本
    """
    metrics = {
        "uptime_seconds": int(_time.time() - _APP_START_TIME),
        "kill_switch_active": kill_switch.is_triggered,
        "pending_order_records": 0,
        "persist_fail_count": {},
        "active_strategies": 0,
        "recent_errors": 0,
        "tick_cache_size": 0,
        "version": "1.1.0",
        "mode": "TESTNET" if settings.EXCHANGE_TESTNET else "LIVE",
    }

    # 1. 订单补偿队列长度（trading_service._pending_order_records）
    try:
        from services.trading_service import _pending_order_records
        metrics["pending_order_records"] = len(_pending_order_records)
    except Exception as e:
        metrics["pending_order_records"] = -1  # -1 表示无法获取

    # 2. Runner 持久化失败计数
    try:
        from strategies.runner import runner
        metrics["persist_fail_count"] = dict(runner._persist_fail_count)
        metrics["active_strategies"] = len(runner._tasks)
    except Exception:
        pass

    # 3. tick_cache 大小
    try:
        from core.tick_cache import tick_cache
        cache = getattr(tick_cache, "_cache", {})
        metrics["tick_cache_size"] = len(cache)
    except Exception:
        pass

    # 4. 最近 5 分钟错误数（从 logger 内存计数，best effort）
    try:
        error_count = getattr(log, "_recent_error_count", 0)
        metrics["recent_errors"] = error_count
    except Exception:
        pass

    # v1.2: 同步到 Prometheus Gauge
    _sync_prometheus(metrics)

    return metrics


def _sync_prometheus(metrics: dict):
    """将 JSON 指标同步到 Prometheus Gauge"""
    try:
        from core.metrics import (
            kill_switch_status as _ks_gauge,
            active_strategies as _as_gauge,
            pending_compensation_queue_size as _pq_gauge,
            tick_cache_size as _tc_gauge,
            app_uptime_seconds as _up_gauge,
            backend_up as _be_gauge,
        )
        _ks_gauge.set(1 if metrics.get("kill_switch_active") else 0)
        _as_gauge.set(metrics.get("active_strategies", 0))
        _pq_gauge.set(max(0, metrics.get("pending_order_records", 0)))
        _tc_gauge.set(metrics.get("tick_cache_size", 0))
        _up_gauge.set(metrics.get("uptime_seconds", 0))
        _be_gauge.set(1)
    except Exception:
        pass


@router.get("/api/metrics/prometheus")
async def get_prometheus_metrics():
    """v1.2: Prometheus scrape 目标端点

    返回 Prometheus 标准文本格式指标。
    用法：在 prometheus.yml 中配置 scrape target 为 /api/metrics/prometheus
    """
    try:
        from core.metrics import get_prometheus_metrics
        data = get_prometheus_metrics()
        return Response(content=data, media_type="text/plain; version=0.0.4")
    except ImportError:
        return Response(
            content=b"# prometheus_client not installed\n",
            status_code=500,
            media_type="text/plain",
        )


@router.get("/api/healthz")
async def healthz():
    """标准命名健康检查 — 探测 DB/Redis/Exchange 依赖

    兼容 Kubernetes / Docker healthcheck 命名约定。
    返回：
      status: "ok" | "degraded" | "down"
      checks: 各依赖项探测结果
    """
    result = {
        "status": "ok",
        "timestamp": _time.time(),
        "checks": {},
    }

    # 1. DB 探测
    try:
        from sqlalchemy import text
        async with async_session() as session:
            start = _time.time()
            await session.execute(text("SELECT 1"))
            latency = int((_time.time() - start) * 1000)
        result["checks"]["database"] = {"ok": True, "latency_ms": latency}
    except Exception as e:
        result["checks"]["database"] = {"ok": False, "error": str(e)[:100]}
        result["status"] = "down"

    # 2. Redis 探测（如果配置了）
    redis_url = getattr(settings, "REDIS_URL", "") or os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            import redis.sync as redis_sync  # type: ignore
            import os as _os
            # 解析 redis://host:port/db
            url_parts = redis_url.replace("redis://", "").split("/")
            host_port = url_parts[0]
            db_num = int(url_parts[1]) if len(url_parts) > 1 else 0
            host, port = host_port.split(":") if ":" in host_port else (host_port, "6379")

            start = _time.time()
            r = redis_sync.Redis(host=host, port=int(port), db=db_num, socket_timeout=2)
            r.ping()
            latency = int((_time.time() - start) * 1000)
            r.close()
            result["checks"]["redis"] = {"ok": True, "latency_ms": latency}
        except ImportError:
            # redis 包未安装，跳过
            result["checks"]["redis"] = {"ok": True, "note": "redis package not installed, skipped"}
        except Exception as e:
            result["checks"]["redis"] = {"ok": False, "error": str(e)[:100]}
            result["status"] = "degraded"
    else:
        result["checks"]["redis"] = {"ok": True, "note": "not configured"}

    # 3. kill_switch 状态
    result["checks"]["kill_switch"] = {
        "ok": not kill_switch.is_triggered,
        "active": kill_switch.is_triggered,
    }
    if kill_switch.is_triggered:
        result["status"] = "degraded"

    # 4. Exchange 最近 tick 时间（best effort）
    try:
        from core.tick_cache import tick_cache
        cache = getattr(tick_cache, "_cache", {})
        if cache:
            latest_ts = max(
                (entry.get("ts", 0) for entry in cache.values() if isinstance(entry, dict)),
                default=0,
            )
            age = int(_time.time() - latest_ts) if latest_ts else -1
            result["checks"]["exchange"] = {
                "ok": age >= 0 and age < 60,
                "latest_tick_age_seconds": age,
            }
            if age >= 60:
                result["status"] = "degraded"
        else:
            result["checks"]["exchange"] = {"ok": True, "note": "no ticks yet (cold start)"}
    except Exception:
        result["checks"]["exchange"] = {"ok": True, "note": "tick_cache not available"}

    return result


# 导入 os（用于 healthz 中的环境变量读取）
import os  # noqa: E402
