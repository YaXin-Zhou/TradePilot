"""策略运行时管理器"""
import asyncio
from typing import Dict
from datetime import datetime, timezone
from strategies.base import SignalType
from db.database import async_session
from db.models import Strategy, StrategyStatus
from sqlalchemy import select
from core.exchange import shared_exchange
from core.risk import risk_manager


class StrategyRunner:
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}

    async def start(self, strategy_id: str, strategy_obj):
        if strategy_id in self._tasks:
            return
        self._tasks[strategy_id] = asyncio.create_task(self._run_loop(strategy_id, strategy_obj))

    async def stop(self, strategy_id: str):
        task = self._tasks.pop(strategy_id, None)
        if task:
            task.cancel()
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                pass
            async with async_session() as session:
                r = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
                s = r.scalar_one_or_none()
                if s:
                    s.status = StrategyStatus.STOPPED
                    s.stopped_at = datetime.now(timezone.utc)
                    await session.commit()

    async def _run_loop(self, sid: str, obj):
        try:
            while True:
                try:
                    t = shared_exchange.fetch_ticker(obj.symbol)
                    signal = await obj.analyze(t)
                    if signal and signal.type not in (SignalType.HOLD,):
                        side = "buy" if signal.type in (SignalType.BUY, SignalType.STRONG_BUY) else "sell"
                        ok, msg = await risk_manager.check_order("system", obj.symbol, side, 100)
                        if ok:
                            shared_exchange.create_market_order(obj.symbol, side, 0.001)
                except Exception:
                    pass
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise

    def is_running(self, strategy_id: str) -> bool:
        t = self._tasks.get(strategy_id)
        return t is not None and not t.done()


runner = StrategyRunner()
