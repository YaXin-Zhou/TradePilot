"""v1.2 Prometheus 指标注册表

导出 Counter / Gauge / Histogram 供 /api/metrics/prometheus 端点抓取。
需要在 lifespan 或业务代码中调用 setter 函数更新指标值。
"""

from prometheus_client import Counter, Gauge, Histogram, generate_latest, REGISTRY
from core.logger import log

# ──── Counter（只增不减）────

trade_orders_total = Counter(
    "trade_orders_total",
    "Total orders placed",
    ["side", "status"],
)

trade_execution_errors_total = Counter(
    "trade_execution_errors_total",
    "Total trade execution errors",
)

audit_events_total = Counter(
    "audit_events_total",
    "Total audit events",
    ["action"],
)

# ──── Gauge（瞬时值）────

active_strategies = Gauge(
    "active_strategies",
    "Number of currently running strategies",
)

pending_compensation_queue_size = Gauge(
    "pending_compensation_queue_size",
    "Pending order compensation queue length",
)

db_pool_size = Gauge(
    "db_pool_size",
    "Database connection pool size",
)

db_pool_checked_out = Gauge(
    "db_pool_checked_out",
    "Database connections checked out",
)

tick_cache_size = Gauge(
    "tick_cache_size",
    "Tick cache entry count",
)

kill_switch_status = Gauge(
    "kill_switch_status",
    "Kill switch state: 0=ARMED, 1=TRIGGERED",
)

online_learner_strategies = Gauge(
    "online_learner_strategies",
    "Number of strategies managed by online learner",
)

app_uptime_seconds = Gauge(
    "app_uptime_seconds",
    "Application uptime in seconds",
)

backend_up = Gauge(
    "backend_up",
    "Backend health status: 0=down, 1=up",
)

# ──── Histogram（分布）────

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0),
)

trade_execution_duration_seconds = Histogram(
    "trade_execution_duration_seconds",
    "Trade execution latency",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

backtest_duration_seconds = Histogram(
    "backtest_duration_seconds",
    "Backtest execution time",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)


def get_prometheus_metrics() -> bytes:
    """生成 Prometheus 格式指标文本"""
    try:
        return generate_latest(REGISTRY)
    except Exception as e:
        log.error(f"Prometheus metrics generation failed: {e}")
        return b""
