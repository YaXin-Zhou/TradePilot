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
                        stmt = MarketData.__table__.insert().prefix_with("OR IGNORE")
                        await session.execute(stmt, {
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


def start_scheduler():
    scheduler.add_job(sync_market_data, IntervalTrigger(hours=1), id="sync_market_data", replace_existing=True)
    scheduler.add_job(retrain_ml_models, IntervalTrigger(hours=24), id="retrain_ml_models", replace_existing=True)
    scheduler.add_job(ai_heartbeat, IntervalTrigger(hours=6), id="ai_heartbeat", replace_existing=True)
    # Phase 8: 任务执行监听（异常隔离 + 记录）
    scheduler.add_listener(_job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    scheduler.start()
    log.info("Scheduler started (market data: 1h, ML retrain: 24h, AI heartbeat: 6h)")


def stop_scheduler():
    try:
        scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
    except Exception:
        pass

