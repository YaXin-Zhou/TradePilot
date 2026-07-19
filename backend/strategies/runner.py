"""策略运行时管理器 — M4 生产加固版

主链路（每 tick）:
  1. kill_switch 检查（触发则拒绝下单）
  2. tick_cache.get → current_price（合并重复请求）
  3. 若持仓: stop_loss_manager.check() → 触发则平仓
  4. analyze → signal
  5. 若有信号: regime_detector → risk_engine.full_check → 金额上限 → portfolio_allocator → create_market_order
  6. 下单后 fetch_order 对账
  7. 持仓状态持久化到 RunnerState 表（DB 行级锁）

M4 改动：
  - runner_state.json 迁入 RunnerState 表（DB 乐观锁 + locked_by/lock_expires）
  - 新增 INSTANCE_ID 实例标识（hostname:pid），支持多实例部署
  - tick 内合并重复请求（tick_cache 消除 fetch_ticker 重复调用）
  - 消除文件锁，崩溃后锁自动过期（LOCK_TTL_SECONDS=60s）
  - 首次启动自动迁移 runner_state.json → DB（迁移后重命名 .migrated）
"""
import asyncio
import json
import os
import socket
import time
from typing import Dict, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
from strategies.base import SignalType
from db.database import async_session
from db.models import Strategy, StrategyStatus, StrategyType, RunnerState
from sqlalchemy import select
from core.exchange import shared_exchange, ExchangeError
from core.logger import log
from core.kill_switch import kill_switch
from core.tick_cache import tick_cache
from config import settings
from services.regime_detector import regime_detector, MarketRegime
from services.risk_engine import risk_engine
from services.stop_loss import StopLossManager, StopLossConfig
from services.portfolio_allocator import portfolio_allocator


# ------------------------------------------------------------------
# M4: 实例标识 + 锁配置
# ------------------------------------------------------------------

INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}"
LOCK_TTL_SECONDS = 60  # 锁过期时间：60s（超过则其他实例可抢占）


def _utcnow_naive() -> datetime:
    """统一返回 naive UTC datetime（与 DB TIMESTAMP WITHOUT TIME ZONE 兼容）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# 旧 JSON 状态文件（仅用于一次性迁移）
_LEGACY_STATE_FILE = Path(__file__).parent.parent / "data" / "runner_state.json"

# 简易 balance 缓存（TTL 1s，消除并行策略 tick 内重复 fetch_balance）
_balance_cache: dict[str, tuple[float, dict]] = {}
_BALANCE_TTL = 1.0


async def _get_cached_balance() -> dict:
    """带 TTL 的 fetch_balance 缓存（消除多策略并行时的重复请求）"""
    key = shared_exchange.name
    now = time.time()
    if key in _balance_cache:
        ts, bal = _balance_cache[key]
        if now - ts < _BALANCE_TTL:
            return bal
    try:
        bal = await asyncio.to_thread(shared_exchange.fetch_balance)
        _balance_cache[key] = (time.time(), bal)
        return bal
    except Exception:
        return {}


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------

class StrategyRunner:
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._stop_managers: Dict[str, StopLossManager] = {}
        self._positions_usdt: Dict[str, float] = {}   # sid → 已分配资金 (USDT)
        self._positions_qty: Dict[str, float] = {}    # sid → 持仓数量 (币)
        self._state_loaded = False

    # ------------------------------------------------------------------
    # M4: 状态持久化（DB 替代 JSON）
    # ------------------------------------------------------------------

    async def _load_persistent_state(self):
        """从 RunnerState 表恢复持仓状态。

        M4: 替代 JSON 文件。首次启动时若 DB 无记录且存在旧 JSON，自动迁移。
        """
        try:
            async with async_session() as session:
                r = await session.execute(select(RunnerState))
                rows = r.scalars().all()

                if not rows and _LEGACY_STATE_FILE.exists():
                    # 首次迁移：JSON → DB
                    await self._migrate_legacy_json(session)

                # 重新查询（迁移后才有数据）
                if not rows:
                    r = await session.execute(select(RunnerState))
                    rows = r.scalars().all()

                for row in rows:
                    sid = row.strategy_id
                    extra = row.extra or {}
                    if "positions_usdt" in extra:
                        self._positions_usdt[sid] = float(extra["positions_usdt"])
                    if row.entry_size is not None:
                        self._positions_qty[sid] = float(row.entry_size)

                if self._positions_usdt:
                    log.info(
                        f"Runner: restored {len(self._positions_usdt)} position states from DB "
                        f"(instance={INSTANCE_ID})"
                    )
                self._state_loaded = True
        except Exception as e:
            log.warning(f"Runner: failed to load state from DB: {e}")
            self._state_loaded = True  # 即使失败也标记已加载，避免阻塞

    async def _migrate_legacy_json(self, session):
        """M4: 一次性迁移 runner_state.json → RunnerState 表"""
        try:
            data = json.loads(_LEGACY_STATE_FILE.read_text(encoding="utf-8"))
            positions_usdt = data.get("positions_usdt", {})
            positions_qty = data.get("positions_qty", {})

            if not positions_usdt and not positions_qty:
                # 空文件，无需迁移
                _rename_legacy_file()
                return

            for sid, usdt_val in positions_usdt.items():
                qty_val = float(positions_qty.get(sid, 0))
                row = RunnerState(
                    strategy_id=sid,
                    position_side="long" if qty_val > 0 else "none",
                    entry_size=qty_val if qty_val > 0 else None,
                    locked_by=None,
                    lock_expires=None,
                    extra={"positions_usdt": float(usdt_val)},
                )
                session.add(row)

            await session.commit()
            log.info(f"Runner: migrated {len(positions_usdt)} states from JSON → DB")
            _rename_legacy_file()
        except Exception as e:
            log.warning(f"Runner: legacy JSON migration failed (non-fatal): {e}")

    async def _persist_state(self, sid: str):
        """持久化单个策略的持仓状态到 RunnerState 表。

        M4: 使用 locked_by/lock_expires 乐观锁，同实例续期。
        """
        try:
            positions_usdt = self._positions_usdt.get(sid, 0.0)
            positions_qty = self._positions_qty.get(sid, 0.0)
            position_side = "long" if positions_qty > 0 else "none"

            async with async_session() as session:
                r = await session.execute(
                    select(RunnerState).where(RunnerState.strategy_id == sid)
                )
                row = r.scalar_one_or_none()
                now = _utcnow_naive()
                lock_expires = now + timedelta(seconds=LOCK_TTL_SECONDS)

                if row is None:
                    row = RunnerState(
                        strategy_id=sid,
                        position_side=position_side,
                        entry_price=None,
                        entry_size=positions_qty if positions_qty > 0 else None,
                        locked_by=INSTANCE_ID,
                        lock_expires=lock_expires,
                        extra={"positions_usdt": positions_usdt},
                    )
                    session.add(row)
                else:
                    row.position_side = position_side
                    row.entry_size = positions_qty if positions_qty > 0 else None
                    # 续期锁（仅当自己持有时）
                    if row.locked_by == INSTANCE_ID or row.locked_by is None:
                        row.locked_by = INSTANCE_ID
                        row.lock_expires = lock_expires
                    row.extra = {"positions_usdt": positions_usdt}

                await session.commit()
        except Exception as e:
            log.error(f"Runner: failed to persist state for {sid}: {e}")

    # ------------------------------------------------------------------
    # M4: 行级锁（乐观锁模式）
    # ------------------------------------------------------------------

    async def _acquire_lock(self, sid: str) -> bool:
        """获取策略锁（M4: 多实例乐观锁）。

        锁获取规则：
          - locked_by == INSTANCE_ID → 续期
          - locked_by IS NULL → 获取
          - lock_expires < now → 抢占（过期锁）
          - 否则 → 拒绝（锁被其他实例持有）
        """
        try:
            async with async_session() as session:
                r = await session.execute(
                    select(RunnerState).where(RunnerState.strategy_id == sid)
                )
                row = r.scalar_one_or_none()
                now = _utcnow_naive()
                lock_expires = now + timedelta(seconds=LOCK_TTL_SECONDS)

                if row is None:
                    row = RunnerState(
                        strategy_id=sid,
                        position_side="none",
                        locked_by=INSTANCE_ID,
                        lock_expires=lock_expires,
                        extra={},
                    )
                    session.add(row)
                elif row.locked_by == INSTANCE_ID:
                    row.lock_expires = lock_expires
                elif row.lock_expires is None or row.lock_expires < now:
                    log.info(
                        f"Runner[{sid}]: acquiring expired/free lock "
                        f"(was held by {row.locked_by})"
                    )
                    row.locked_by = INSTANCE_ID
                    row.lock_expires = lock_expires
                else:
                    log.warning(
                        f"Runner[{sid}]: lock held by {row.locked_by}, "
                        f"expires at {row.lock_expires}"
                    )
                    await session.rollback()
                    return False

                await session.commit()
                return True
        except Exception as e:
            log.error(f"Runner[{sid}]: failed to acquire lock: {e}")
            return False

    async def _release_lock(self, sid: str):
        """释放策略锁（仅当自己持有时）"""
        try:
            async with async_session() as session:
                r = await session.execute(
                    select(RunnerState).where(RunnerState.strategy_id == sid)
                )
                row = r.scalar_one_or_none()
                if row and row.locked_by == INSTANCE_ID:
                    row.locked_by = None
                    row.lock_expires = None
                    await session.commit()
        except Exception as e:
            log.warning(f"Runner[{sid}]: failed to release lock: {e}")

    async def _renew_lock(self, sid: str):
        """续期锁（每个 tick 调用，防止运行中过期）"""
        try:
            async with async_session() as session:
                r = await session.execute(
                    select(RunnerState).where(RunnerState.strategy_id == sid)
                )
                row = r.scalar_one_or_none()
                if row and row.locked_by == INSTANCE_ID:
                    row.lock_expires = _utcnow_naive() + timedelta(
                        seconds=LOCK_TTL_SECONDS
                    )
                    await session.commit()
        except Exception as e:
            log.warning(f"Runner[{sid}]: failed to renew lock: {e}")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self, strategy_id: str, strategy_obj):
        if strategy_id in self._tasks:
            return
        if kill_switch.is_triggered:
            log.warning(f"StrategyRunner[{strategy_id}]: KILL SWITCH triggered, refuse to start")
            return
        # M4: 确保状态已加载
        if not self._state_loaded:
            await self._load_persistent_state()
        # M4: 获取行级锁
        if not await self._acquire_lock(strategy_id):
            log.warning(f"StrategyRunner[{strategy_id}]: cannot acquire lock, refuse to start")
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
                    s.stopped_at = _utcnow_naive()
                    await session.commit()
            # 清理止损状态（保留持仓记录用于恢复）
            self._stop_managers.pop(strategy_id, None)
            await self._persist_state(strategy_id)
            await self._release_lock(strategy_id)

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
        """启动时恢复所有 status=RUNNING 的策略。

        M4: 进程崩溃重启后，自动恢复之前运行中的策略。
        锁过期机制保证：崩溃实例持有的锁在 60s 后自动释放。
        """
        try:
            # M4: 先加载持久化状态
            if not self._state_loaded:
                await self._load_persistent_state()

            async with async_session() as session:
                r = await session.execute(
                    select(Strategy).where(Strategy.status == StrategyStatus.RUNNING)
                )
                strategies = r.scalars().all()

            if not strategies:
                log.info("Runner: no RUNNING strategies to recover")
                return 0

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
        """M4: 使用 balance 缓存，消除多策略并行时的重复请求"""
        try:
            bal = await _get_cached_balance()
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
        log.info(f"StrategyRunner[{sid}]: started for {obj.symbol} (instance={INSTANCE_ID})")
        try:
            while True:
                try:
                    if kill_switch.is_triggered:
                        log.warning(f"StrategyRunner[{sid}]: KILL SWITCH triggered, stopping")
                        break
                    # M4: 续期锁（每个 tick）
                    await self._renew_lock(sid)
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
            await self._persist_state(sid)

    async def _tick(self, sid: str, obj):
        # M4: 1. 获取当前价格（tick_cache 合并重复请求）
        t = await tick_cache.get(shared_exchange, obj.symbol)
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

        # 6. 金额硬上限检查
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

            # 对账（fetch_order 校验订单真实存在）
            if order.get("id"):
                try:
                    verified = await asyncio.to_thread(
                        shared_exchange.fetch_order, order["id"], obj.symbol
                    )
                    if verified:
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

        # 10. 更新持仓记录 + 持久化（M4: DB）
        self._positions_usdt[sid] = current_position + order_usdt
        self._positions_qty[sid] = self._positions_qty.get(sid, 0.0) + order_amount
        await self._persist_state(sid)

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
        # 清理状态 + 持久化（M4: DB）
        self._stop_managers.pop(sid, None)
        self._positions_usdt.pop(sid, None)
        self._positions_qty.pop(sid, None)
        await self._persist_state(sid)

    def is_running(self, strategy_id: str) -> bool:
        t = self._tasks.get(strategy_id)
        return t is not None and not t.done()

    def get_positions(self) -> dict:
        """获取所有策略持仓状态（供 API 查询）"""
        return {
            "positions_usdt": dict(self._positions_usdt),
            "positions_qty": dict(self._positions_qty),
            "running_strategies": list(self._tasks.keys()),
            "instance_id": INSTANCE_ID,
        }


# ------------------------------------------------------------------
# M4: 旧 JSON 迁移辅助
# ------------------------------------------------------------------

def _rename_legacy_file():
    """迁移完成后重命名 JSON 文件，避免重复迁移"""
    try:
        migrated = _LEGACY_STATE_FILE.with_suffix(".json.migrated")
        _LEGACY_STATE_FILE.rename(migrated)
        log.info(f"Runner: renamed legacy state file → {migrated.name}")
    except Exception as e:
        log.warning(f"Runner: failed to rename legacy state file: {e}")


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
