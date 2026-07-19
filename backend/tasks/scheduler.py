import asyncio
"""APScheduler 定时任务"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone

scheduler = AsyncIOScheduler()


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
            except Exception:
                pass


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
                await asyncio.to_thread(train_model, symbol, "1h", 1000)
            except Exception:
                pass


def start_scheduler():
    scheduler.add_job(sync_market_data, IntervalTrigger(hours=1), id="sync_market_data", replace_existing=True)
    scheduler.add_job(retrain_ml_models, IntervalTrigger(hours=24), id="retrain_ml_models", replace_existing=True)
    scheduler.start()


def stop_scheduler():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass

