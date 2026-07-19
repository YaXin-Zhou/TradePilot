"""策略运行时管理器 — Phase 7.3 接入 regime_detector + risk_engine + stop_loss + portfolio_allocator

主链路（每 tick）:
  1. fetch_ticker → current_price
  2. 若持仓: stop_loss_manager.check() → 触发则平仓
  3. analyze → signal
  4. 若有信号: regime_detector → risk_engine.full_check → portfolio_allocator.allocate → create_market_order

修复历史问题:
  - 去掉硬编码 0.001 下单数量（改用 portfolio_allocator 计算）
  - 修复 except Exception: pass 异常吞噬（改为 log.error）
  - 接入 stop_loss_manager 四级止损
"""
import asyncio
import time
from typing import Dict, Optional
from datetime import datetime, timezone
from strategies.base import SignalType
from db.database import async_session
from db.models import Strategy, StrategyStatus, StrategyType
from sqlalchemy import select
from core.exchange import shared_exchange
from core.logger import log
from services.regime_detector import regime_detector, MarketRegime
from services.risk_engine import risk_engine
from services.stop_loss import StopLossManager, StopLossConfig
from services.portfolio_allocator import portfolio_allocator


class StrategyRunner:
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._stop_managers: Dict[str, StopLossManager] = {}
        self._positions_usdt: Dict[str, float] = {}   # sid → 已分配资金 (USDT)
        self._positions_qty: Dict[str, float] = {}    # sid → 持仓数量 (币)

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
            # 清理止损状态
            self._stop_managers.pop(strategy_id, None)
            self._positions_usdt.pop(strategy_id, None)
            self._positions_qty.pop(strategy_id, None)

    # ------------------------------------------------------------------
    # 辅助：数据获取
    # ------------------------------------------------------------------

    async def _detect_regime(self, symbol: str) -> MarketRegime:
        try:
            df = await asyncio.to_thread(shared_exchange.fetch_ohlcv, symbol, "1h", 200)
            if df is None or df.empty:
                return MarketRegime.RANGING_LOW_VOL
            return regime_detector.detect(df.to_dict("records"), symbol).regime
        except Exception as e:
            log.warning(f"Runner: regime detect failed for {symbol}: {e}")
            return MarketRegime.RANGING_LOW_VOL

    async def _get_total_capital(self) -> float:
        try:
            bal = await asyncio.to_thread(shared_exchange.fetch_balance)
            return bal.get("USDT", {}).get("total", 10000.0)
        except Exception:
            return 10000.0

    def _get_strategy_weight(self, strategy_id: str) -> float:
        """从策略池获取权重，拿不到默认 0.1"""
        try:
            from services.strategy_pool import strategy_pool
            s = strategy_pool.get(strategy_id)
            if s:
                return s.weight
        except Exception:
            pass
        return 0.1

    @staticmethod
    def _resolve_strategy_type(obj) -> str:
        """从策略对象解析 strategy_type 字符串"""
        st = getattr(obj, "strategy_type", None)
        if st is None:
            return StrategyType.CUSTOM.value
        if hasattr(st, "value"):
            return st.value
        return str(st)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def _run_loop(self, sid: str, obj):
        log.info(f"StrategyRunner[{sid}]: started for {obj.symbol}")
        try:
            while True:
                try:
                    await self._tick(sid, obj)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    # Phase 7.3: 修复异常吞噬 — 记录日志而非 pass
                    log.error(f"StrategyRunner[{sid}] tick error: {e}")
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            log.info(f"StrategyRunner[{sid}]: stopped")
            raise

    async def _tick(self, sid: str, obj):
        # 1. 获取当前价格
        t = await asyncio.to_thread(shared_exchange.fetch_ticker, obj.symbol)
        current_price = t.get("last", 0) or 0
        if current_price <= 0:
            return

        # 2. 止损检查（若持仓）
        if sid in self._stop_managers:
            sm = self._stop_managers[sid]
            sm.update_price(current_price)
            result = sm.check()
            if result.triggered:
                log.warning(f"StrategyRunner[{sid}] stop loss: {result.message}")
                await self._close_position(sid, obj.symbol, sm.side)
                return

        # 3. 分析信号
        signal = await obj.analyze(t)
        if not signal or signal.type == SignalType.HOLD:
            return

        side = "buy" if signal.type in (SignalType.BUY, SignalType.STRONG_BUY) else "sell"

        # 4. 风控 + 仓位计算
        regime = await self._detect_regime(obj.symbol)
        total_capital = await self._get_total_capital()
        strategy_type = self._resolve_strategy_type(obj)
        weight = self._get_strategy_weight(sid)
        current_position = self._positions_usdt.get(sid, 0.0)

        # 5. portfolio_allocator 计算分配金额
        plan = portfolio_allocator.allocate(
            weights={sid: weight},
            total_capital=total_capital,
            current_positions={sid: current_position},
            regime=regime,
        )
        allocation = next((a for a in plan.allocations if a.strategy_id == sid), None)
        if not allocation or allocation.amount <= 0:
            return  # hold 或无需调整
        order_usdt = abs(allocation.amount)
        order_amount = order_usdt / current_price

        # 6. risk_engine 全链路检查
        sharpe = getattr(obj, "sharpe_oos", 1.0)
        risk_result = risk_engine.full_check(
            regime=regime,
            strategy_type=strategy_type,
            sharpe_oos=sharpe,
            total_capital=total_capital,
            current_position=current_position,
            new_amount=order_usdt,
            strategy_position=current_position,
            daily_pnl=0.0,
            user_id="system",
        )
        if not risk_result.passed:
            log.info(f"StrategyRunner[{sid}] risk blocked: {risk_result.reason}")
            return

        # 7. 下单
        try:
            await asyncio.to_thread(
                shared_exchange.create_market_order, obj.symbol, side, order_amount
            )
            log.info(f"StrategyRunner[{sid}] order: {side} {order_amount:.6f} "
                     f"(@{current_price:.2f} = ${order_usdt:.2f})")
        except Exception as e:
            log.error(f"StrategyRunner[{sid}] order failed: {e}")
            return

        # 8. 初始化/更新止损状态机
        policy = risk_engine.get_policy(regime)
        sl_config = StopLossConfig.from_policy(policy)
        side_str = "long" if side == "buy" else "short"
        if sid in self._stop_managers:
            sm = self._stop_managers[sid]
            sm.reset(current_price)
            sm.set_side(side_str)
        else:
            sm = StopLossManager(sl_config, current_price)
            sm.set_side(side_str)
            self._stop_managers[sid] = sm

        # 更新持仓记录
        self._positions_usdt[sid] = current_position + order_usdt
        self._positions_qty[sid] = self._positions_qty.get(sid, 0.0) + order_amount

    async def _close_position(self, sid: str, symbol: str, side: str):
        """平仓"""
        qty = self._positions_qty.get(sid, 0.0)
        if qty <= 0:
            return
        close_side = "sell" if side == "long" else "buy"
        try:
            await asyncio.to_thread(
                shared_exchange.create_market_order, symbol, close_side, qty
            )
            log.info(f"StrategyRunner[{sid}] close position: {close_side} {qty:.6f}")
        except Exception as e:
            log.error(f"StrategyRunner[{sid}] close failed: {e}")
            return
        # 清理状态
        self._stop_managers.pop(sid, None)
        self._positions_usdt.pop(sid, None)
        self._positions_qty.pop(sid, None)

    def is_running(self, strategy_id: str) -> bool:
        t = self._tasks.get(strategy_id)
        return t is not None and not t.done()


runner = StrategyRunner()
