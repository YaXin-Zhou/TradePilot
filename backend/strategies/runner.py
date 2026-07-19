"""策略运行时管理器 — Phase 8 实盘就绪版

主链路（每 tick）:
  1. kill_switch 检查（触发则拒绝下单）
  2. fetch_ticker → current_price
  3. 若持仓: stop_loss_manager.check() → 触发则平仓
  4. analyze → signal
  5. 若有信号: regime_detector → risk_engine.full_check → 金额上限 → portfolio_allocator → create_market_order
  6. 下单后 fetch_order 对账
  7. 持仓状态持久化到 JSON

Phase 8 改动：
  - 持仓状态持久化到 data/runner_state.json（崩溃不丢）
  - 恢复 RUNNING 策略：startup 时从 DB 查 status=RUNNING 的策略自动重启
  - kill_switch 触发时停止所有策略
  - 金额硬上限检查
  - 下单后对账（fetch_order 校验）
"""
import asyncio
import json
import time
from typing import Dict, Optional
from datetime import datetime, timezone
from pathlib import Path
from strategies.base import SignalType
from db.database import async_session
from db.models import Strategy, StrategyStatus, StrategyType
from sqlalchemy import select
from core.exchange import shared_exchange, ExchangeError
from core.logger import log
from core.kill_switch import kill_switch
from config import settings
from services.regime_detector import regime_detector, MarketRegime
from services.risk_engine import risk_engine
from services.stop_loss import StopLossManager, StopLossConfig
from services.portfolio_allocator import portfolio_allocator


# ------------------------------------------------------------------
# 状态持久化
# ------------------------------------------------------------------

STATE_FILE = Path(__file__).parent.parent / "data" / "runner_state.json"


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Runner: failed to load state: {e}")
    return {"positions_usdt": {}, "positions_qty": {}, "stop_states": {}}


def _save_state(state: dict):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.error(f"Runner: failed to save state: {e}")


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------

class StrategyRunner:
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._stop_managers: Dict[str, StopLossManager] = {}
        self._positions_usdt: Dict[str, float] = {}   # sid → 已分配资金 (USDT)
        self._positions_qty: Dict[str, float] = {}    # sid → 持仓数量 (币)
        self._load_persistent_state()

    def _load_persistent_state(self):
        """从持久化文件恢复持仓状态"""
        state = _load_state()
        self._positions_usdt = {k: float(v) for k, v in state.get("positions_usdt", {}).items()}
        self._positions_qty = {k: float(v) for k, v in state.get("positions_qty", {}).items()}
        if self._positions_usdt:
            log.info(f"Runner: restored {len(self._positions_usdt)} position states from disk")

    def _persist_state(self):
        """持久化持仓状态"""
        _save_state({
            "positions_usdt": self._positions_usdt,
            "positions_qty": self._positions_qty,
            "updated_at": time.time(),
        })

    async def start(self, strategy_id: str, strategy_obj):
        if strategy_id in self._tasks:
            return
        # kill_switch 检查
        if kill_switch.is_triggered:
            log.warning(f"StrategyRunner[{strategy_id}]: KILL SWITCH triggered, refuse to start")
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
            # 清理止损状态（保留持仓记录用于恢复）
            self._stop_managers.pop(strategy_id, None)
            self._persist_state()

    async def stop_all(self) -> int:
        """停止所有运行中策略（紧急停止用）"""
        n = 0
        for sid in list(self._tasks.keys()):
            try:
                await self.stop(sid)
                n += 1
            except Exception as e:
                log.error(f"Runner: stop_all failed for {sid}: {e}")
        return n

    async def recover_running_strategies(self):
        """启动时恢复所有 status=RUNNING 的策略

        Phase 8: 进程崩溃重启后，自动恢复之前运行中的策略。
        """
        try:
            async with async_session() as session:
                r = await session.execute(
                    select(Strategy).where(Strategy.status == StrategyStatus.RUNNING)
                )
                strategies = r.scalars().all()

            if not strategies:
                log.info("Runner: no RUNNING strategies to recover")
                return 0

            # kill_switch 触发时不恢复
            if kill_switch.is_triggered:
                log.warning(
                    f"Runner: KILL SWITCH triggered, marking {len(strategies)} "
                    "RUNNING strategies as STOPPED (not recovered)"
                )
                async with async_session() as session:
                    for s in strategies:
                        s.status = StrategyStatus.STOPPED
                    await session.commit()
                return 0

            recovered = 0
            for s in strategies:
                try:
                    obj = _build_strategy_obj(s)
                    if obj:
                        await self.start(s.id, obj)
                        recovered += 1
                        log.info(f"Runner: recovered strategy {s.id} ({s.name})")
                except Exception as e:
                    log.error(f"Runner: recover {s.id} failed: {e}")

            log.info(f"Runner: recovered {recovered}/{len(strategies)} RUNNING strategies")
            return recovered
        except Exception as e:
            log.error(f"Runner: recover_running_strategies failed: {e}")
            return 0

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
            return bal.get("USDT", {}).get("total", 0.0)
        except Exception:
            return 0.0

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
                    # kill_switch 触发则停止
                    if kill_switch.is_triggered:
                        log.warning(f"StrategyRunner[{sid}]: KILL SWITCH triggered, stopping")
                        break
                    await self._tick(sid, obj)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.error(f"StrategyRunner[{sid}] tick error: {e}")
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            log.info(f"StrategyRunner[{sid}]: stopped")
            raise
        finally:
            self._persist_state()

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
        if total_capital <= 0:
            log.warning(f"StrategyRunner[{sid}]: total capital = 0, skip")
            return
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

        # 6. 金额硬上限检查（Phase 8）
        if order_usdt > settings.MAX_ORDER_AMOUNT_USDT:
            order_usdt = settings.MAX_ORDER_AMOUNT_USDT
            log.info(f"StrategyRunner[{sid}]: capped order to {order_usdt} (hard limit)")

        order_amount = order_usdt / current_price

        # 7. risk_engine 全链路检查
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

        # 8. 下单 + 对账
        try:
            order = await asyncio.to_thread(
                shared_exchange.create_market_order, obj.symbol, side, order_amount
            )
            log.info(f"StrategyRunner[{sid}] order: {side} {order_amount:.6f} "
                     f"(@{current_price:.2f} = ${order_usdt:.2f}) id={order.get('id')}")

            # Phase 8: 对账（fetch_order 校验订单真实存在）
            if order.get("id"):
                try:
                    verified = await asyncio.to_thread(
                        shared_exchange.fetch_order, order["id"], obj.symbol
                    )
                    if verified:
                        # 用交易所返回的实际成交价/数量更新
                        actual_filled = float(verified.get("filled", 0) or order_amount)
                        actual_cost = float(verified.get("cost", 0) or order_usdt)
                        order_amount = actual_filled
                        order_usdt = actual_cost if actual_cost > 0 else order_usdt
                        log.info(f"StrategyRunner[{sid}] order verified: filled={actual_filled}")
                    else:
                        log.warning(f"StrategyRunner[{sid}] order verification returned None")
                except Exception as e:
                    log.warning(f"StrategyRunner[{sid}] order verify failed (non-fatal): {e}")

        except ExchangeError as e:
            log.error(f"StrategyRunner[{sid}] order FAILED: {e}")
            return
        except Exception as e:
            log.error(f"StrategyRunner[{sid}] order exception: {e}")
            return

        # 9. 初始化/更新止损状态机
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

        # 10. 更新持仓记录 + 持久化
        self._positions_usdt[sid] = current_position + order_usdt
        self._positions_qty[sid] = self._positions_qty.get(sid, 0.0) + order_amount
        self._persist_state()

    async def _close_position(self, sid: str, symbol: str, side: str):
        """平仓"""
        qty = self._positions_qty.get(sid, 0.0)
        if qty <= 0:
            return
        close_side = "sell" if side == "long" else "buy"
        try:
            order = await asyncio.to_thread(
                shared_exchange.create_market_order, symbol, close_side, qty
            )
            log.info(f"StrategyRunner[{sid}] close position: {close_side} {qty:.6f} id={order.get('id')}")

            # 对账
            if order.get("id"):
                try:
                    verified = await asyncio.to_thread(
                        shared_exchange.fetch_order, order["id"], symbol
                    )
                    if verified:
                        actual_filled = float(verified.get("filled", 0) or qty)
                        qty = actual_filled
                except Exception:
                    pass

        except ExchangeError as e:
            log.error(f"StrategyRunner[{sid}] close FAILED: {e}")
            return
        except Exception as e:
            log.error(f"StrategyRunner[{sid}] close exception: {e}")
            return
        # 清理状态 + 持久化
        self._stop_managers.pop(sid, None)
        self._positions_usdt.pop(sid, None)
        self._positions_qty.pop(sid, None)
        self._persist_state()

    def is_running(self, strategy_id: str) -> bool:
        t = self._tasks.get(strategy_id)
        return t is not None and not t.done()

    def get_positions(self) -> dict:
        """获取所有策略持仓状态（供 API 查询）"""
        return {
            "positions_usdt": dict(self._positions_usdt),
            "positions_qty": dict(self._positions_qty),
            "running_strategies": list(self._tasks.keys()),
        }


# ------------------------------------------------------------------
# 策略对象构建（从 DB Strategy 记录重建运行时对象）
# ------------------------------------------------------------------

def _build_strategy_obj(strategy: Strategy):
    """从 DB Strategy 记录构建运行时策略对象。

    根据 strategy.type 实例化对应的策略类。
    """
    try:
        from strategies.grid_strategy import GridStrategy
        from strategies.ma_cross import MACrossStrategy
        from strategies.rsi_strategy import RSIStrategy
        from strategies.bollinger import BollingerStrategy

        config = strategy.config or {}
        stype = strategy.type

        if stype == StrategyType.GRID:
            return GridStrategy(
                symbol=strategy.symbol,
                lower=config.get("lower", settings.DEFAULT_GRID_LOWER),
                upper=config.get("upper", settings.DEFAULT_GRID_UPPER),
                grid_count=config.get("grid_count", settings.DEFAULT_GRID_COUNT),
            )
        elif stype == StrategyType.MA_CROSS or stype == StrategyType.SMA_CROSS:
            return MACrossStrategy(
                symbol=strategy.symbol,
                fast=config.get("fast", 7),
                slow=config.get("slow", 25),
            )
        elif stype == StrategyType.RSI:
            return RSIStrategy(
                symbol=strategy.symbol,
                period=config.get("period", 14),
                oversold=config.get("oversold", 30),
                overbought=config.get("overbought", 70),
            )
        elif stype == StrategyType.BOLLINGER:
            return BollingerStrategy(
                symbol=strategy.symbol,
                period=config.get("period", 20),
                std=config.get("std", 2.0),
            )
        else:
            log.warning(f"Runner: cannot build strategy obj for type {stype}, skip")
            return None
    except Exception as e:
        log.error(f"Runner: build_strategy_obj failed for {getattr(strategy, 'id', '?')}: {e}")
        return None


runner = StrategyRunner()
