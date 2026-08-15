import asyncio
"""APScheduler 定时任务 — Phase 8 任务隔离 + 执行记录"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from datetime import datetime, timezone
from core.logger import log

scheduler = AsyncIOScheduler()


def _job_listener(event):
    """任务执行监听器 — 记录异常和执行情况（Phase 8: 任务隔离）"""
    if event.exception:
        log.error(f"Scheduler job {event.job_id} FAILED: {event.exception}")
    else:
        log.debug(f"Scheduler job {event.job_id} executed OK")


async def sync_market_data():
    """每小时同步活跃策略的 K 线数据"""
    from db.database import async_session
    from db.models import Strategy, StrategyStatus, MarketData
    from sqlalchemy import select
    from core.exchange import shared_exchange
    from config import settings

    # v2.0: 跨数据库 upsert（SQLite 用 OR IGNORE，PostgreSQL 用 ON CONFLICT DO NOTHING）
    if "sqlite" in settings.DATABASE_URL.lower():
        insert_stmt = MarketData.__table__.insert().prefix_with("OR IGNORE")
    else:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        insert_stmt = pg_insert(MarketData.__table__).on_conflict_do_nothing(
            index_elements=["symbol", "timeframe", "timestamp"]
        )

    async with async_session() as session:
        result = await session.execute(
            select(Strategy).where(Strategy.status == StrategyStatus.RUNNING)
        )
        strategies = result.scalars().all()
        for s in strategies:
            try:
                df = await asyncio.to_thread(shared_exchange.fetch_ohlcv, s.symbol, "1h", 200)
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        ts = row["timestamp"]
                        if isinstance(ts, datetime):
                            ts = ts.replace(tzinfo=timezone.utc)
                        await session.execute(insert_stmt, {
                            "symbol": s.symbol, "timeframe": "1h",
                            "timestamp": ts, "open": row["open"],
                            "high": row["high"], "low": row["low"],
                            "close": row["close"], "volume": row["volume"],
                        })
                    await session.commit()
            except Exception as e:
                log.warning(f"Market data sync failed for {s.symbol}: {e}")


async def retrain_ml_models():
    """每24小时重训练ML模型"""
    from db.database import async_session
    from db.models import Strategy, StrategyStatus
    from sqlalchemy import select
    from ml.models import train_model

    async with async_session() as session:
        result = await session.execute(
            select(Strategy).where(Strategy.status == StrategyStatus.RUNNING)
        )
        symbols = set(s.symbol for s in result.scalars().all())
        for symbol in symbols:
            try:
                log.info(f"Retraining ML model for {symbol}")
                await asyncio.to_thread(train_model, symbol, "1h", 1000)
            except Exception as e:
                log.error(f"ML retrain failed for {symbol}: {e}")


async def ai_heartbeat():
    """每6小时 AI 心跳审查策略池"""
    try:
        from tasks.ai_heartbeat import get_heartbeat
        hb = get_heartbeat()
        result = await hb.beat()
        log.info(f"AI Heartbeat: cycle #{result.cycle} done, "
                 f"{len(result.recommendations)} recommendations")
    except Exception as e:
        log.error(f"AI Heartbeat failed: {e}")


async def refresh_kill_switch():
    """P0-1 + P1-3: 每 5 秒从 DB 刷新 kill_switch + risk_engine + online_learner + strategy_pool

    多 worker 场景下，一个 worker 修改状态后，其他 worker 通过此任务检测到变化。
    """
    try:
        from core.kill_switch import kill_switch
        from services.risk_engine import risk_engine
        await kill_switch.refresh_from_db()
        await risk_engine.refresh_from_db()
    except Exception as e:
        log.debug(f"Kill switch refresh failed: {e}")

    try:
        from services.online_learner import online_learner
        from services.strategy_pool import strategy_pool
        await online_learner.refresh_from_db()
        await strategy_pool.refresh_from_db()
    except Exception as e:
        log.debug(f"Pool/learner refresh failed: {e}")


async def flush_pending_orders():
    """P1-2: 每 30 秒补偿 DB 写入失败的订单记录

    下单成功但 DB 落库失败的订单会进入内存队列，
    此任务定期重试，确保资金对账数据最终一致。
    """
    try:
        from services.trading_service import flush_pending_order_records
        await flush_pending_order_records()
    except Exception as e:
        log.debug(f"Pending orders flush failed: {e}")


async def flush_strategy_logs():
    """每 10 秒将策略日志内存队列刷入 DB"""
    try:
        from services.strategy_log import flush_to_db
        n = await flush_to_db()
        if n:
            log.debug(f"StrategyLog flushed: {n} events")
    except Exception as e:
        log.debug(f"StrategyLog flush failed: {e}")


async def system_heartbeat():
    """系统心跳日志 — 每 60 秒输出系统整体运行状态。

    包含：运行中策略数、持仓数、交易所连接状态、kill_switch 状态、
    内存队列状态、DB 订单数。便于运维快速判断系统是否健康。
    """
    try:
        from core.exchange import shared_exchange
        from core.kill_switch import kill_switch
        from services.trading_service import _pending_order_records

        # 运行中策略 + 持仓
        running = 0
        positions = 0
        try:
            from strategies.runner import runner
            running = len(runner._tasks)
            positions = len(runner._positions_usdt)
        except Exception as e:
            log.warning(f"获取策略运行状态失败: {e}")

        # 交易所连接状态
        exchange_ok = shared_exchange._connected if hasattr(shared_exchange, '_connected') else False
        exchange_name = shared_exchange.name if hasattr(shared_exchange, 'name') else '?'

        # kill_switch
        ks_status = kill_switch.get_state().get("status", "?")

        # 内存队列
        pending = len(_pending_order_records)

        # DB 订单数
        db_orders = -1
        try:
            from db.database import async_session
            from db.models import Order
            from sqlalchemy import select, func
            async with async_session() as session:
                db_orders = await session.scalar(select(func.count(Order.id))) or 0
        except Exception as e:
            log.warning(f"统计DB订单数失败: {e}")

        log.info(
            f"[HEARTBEAT] running_strategies={running} positions={positions} "
            f"exchange={exchange_name}({'ok' if exchange_ok else 'OFFLINE'}) "
            f"kill_switch={ks_status} pending_orders={pending} "
            f"db_orders={db_orders} instance_ok"
        )
    except Exception as e:
        log.warning(f"[HEARTBEAT] failed: {e}")


def start_scheduler():
    scheduler.add_job(sync_market_data, IntervalTrigger(hours=1), id="sync_market_data", replace_existing=True)
    scheduler.add_job(retrain_ml_models, IntervalTrigger(hours=24), id="retrain_ml_models", replace_existing=True)
    scheduler.add_job(ai_heartbeat, IntervalTrigger(hours=6), id="ai_heartbeat", replace_existing=True)
    # P0-1: kill_switch + risk_engine 多 worker 状态同步（每 5 秒刷新）
    scheduler.add_job(refresh_kill_switch, IntervalTrigger(seconds=5), id="refresh_kill_switch", replace_existing=True)
    # P1-2: 订单落库失败补偿（每 30 秒重试内存队列）
    scheduler.add_job(flush_pending_orders, IntervalTrigger(seconds=30), id="flush_pending_orders", replace_existing=True)
    # 系统心跳日志（每 60 秒输出运行状态）
    scheduler.add_job(system_heartbeat, IntervalTrigger(seconds=60), id="system_heartbeat", replace_existing=True)
    # 策略日志刷盘（每 10 秒将内存队列写入 DB）
    scheduler.add_job(flush_strategy_logs, IntervalTrigger(seconds=10), id="flush_strategy_logs", replace_existing=True)
    # Phase 8: 任务执行监听（异常隔离 + 记录）
    scheduler.add_listener(_job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    scheduler.start()
    log.info("Scheduler started (market data: 1h, ML retrain: 24h, AI heartbeat: 6h, "
             "kill_switch refresh: 5s, pending orders flush: 30s, system heartbeat: 60s, strategy log flush: 10s)")


def stop_scheduler():
    try:
        scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
    except Exception as e:
        log.warning(f"关闭调度器失败: {e}")

