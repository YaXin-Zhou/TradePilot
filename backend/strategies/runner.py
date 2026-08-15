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
from db.models import Strategy, StrategyStatus, StrategyType, RunnerState, OrderType, Trade
from sqlalchemy import select
import core.exchange as exmod
from core.exchange import ExchangeError
from core.logger import log
from core.kill_switch import kill_switch
from core.tick_cache import tick_cache
from config import settings
from services.regime_detector import regime_detector, MarketRegime
from services.risk_engine import risk_engine
from services.strategy_log import append as log_event
from services.alert_service import alert_service
from services.stop_loss import StopLossManager, StopLossConfig
from services.portfolio_allocator import portfolio_allocator


# ------------------------------------------------------------------
# M4: 实例标识 + 锁配置
# ------------------------------------------------------------------

INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}"
LOCK_TTL_SECONDS = 60  # 锁过期时间：60s（超过则其他实例可抢占）


def _db_supports_row_lock() -> bool:
    """PostgreSQL 支持 SELECT ... FOR UPDATE（行级锁），SQLite 不支持"""
    return "postgresql" in settings.DATABASE_URL.lower()


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
    key = exmod.shared_exchange.name
    now = time.time()
    if key in _balance_cache:
        ts, bal = _balance_cache[key]
        if now - ts < _BALANCE_TTL:
            return bal
    try:
        bal = await asyncio.to_thread(exmod.shared_exchange.fetch_balance)
        _balance_cache[key] = (time.time(), bal)
        return bal
    except Exception as e:
        log.debug(f"fetch_balance_from_exchange failed: {e}")
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
        self._persist_fail_count: Dict[str, int] = {}  # P1-2: 持久化失败计数
        # v1.3 U4: 多交易对支持
        self._symbol_map: Dict[str, str] = {}  # strategy_id → symbol

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
                # P1-2: 成功后清除失败计数
                self._persist_fail_count.pop(sid, None)
        except Exception as e:
            # P1-2: 不再静默吞掉 — 连续失败计数 + 阈值告警
            fail_count = self._persist_fail_count.get(sid, 0) + 1
            self._persist_fail_count[sid] = fail_count
            if fail_count >= 3:
                log.warning(
                    f"Runner[{sid}] state persist FAILED {fail_count}x — "
                    f"position may be lost on restart! Error: {e}"
                )
            else:
                log.error(f"Runner[{sid}] state persist failed ({fail_count}x): {e}")

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
                # v2.0: 行级锁（FOR UPDATE）保证"读-改-写"原子，防多实例重复获取
                stmt = select(RunnerState).where(RunnerState.strategy_id == sid)
                if _db_supports_row_lock():
                    stmt = stmt.with_for_update()
                r = await session.execute(stmt)
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

    async def start(self, strategy_id: str, strategy_obj, symbol: str = ""):
        if strategy_id in self._tasks:
            return
        # v1.3 U4: 记录 symbol 映射
        if symbol:
            self._symbol_map[strategy_id] = symbol
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

    async def shutdown(self):
        """v1.1 优雅关闭：停止全部策略 + 持久化所有持仓状态"""
        log.info("Runner: graceful shutdown — stopping all strategies...")
        stopped = await self.stop_all()
        log.info(f"Runner: stopped {stopped} strategies")
        # 最终持久化（确保剩余持仓不丢失）
        for sid in list(self._positions_usdt.keys()):
            try:
                await self._persist_state(sid)
            except Exception as e:
                log.error(f"Runner: final persist failed for {sid}: {e}")
        log.info("Runner: shutdown complete")

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
            df = await asyncio.to_thread(exmod.shared_exchange.fetch_ohlcv, symbol, "1h", 200)
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
        except Exception as e:
            log.debug(f"USDT balance read failed: {e}")
            return 0.0

    def _get_strategy_weight(self, strategy_id: str) -> float:
        """从策略池获取权重，拿不到默认 0.1"""
        try:
            from services.strategy_pool import strategy_pool
            s = strategy_pool.get(strategy_id)
            if s:
                return s.weight
        except Exception as e:
            log.debug(f"strategy weight lookup failed for {strategy_id}: {e}")
        return 0.1

    async def _get_daily_pnl(self) -> float:
        """当日已实现盈亏（v2.0: 由 Trade 表汇总，供日亏损熔断，不再恒 0）"""
        try:
            from datetime import datetime, timezone as _tz
            from sqlalchemy import select, func
            from db.models import Trade
            start = (
                datetime.now(_tz.utc)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .replace(tzinfo=None)
            )
            async with async_session() as session:
                val = await session.scalar(
                    select(func.coalesce(func.sum(Trade.profit), 0.0)).where(
                        Trade.closed_at >= start
                    )
                )
                return float(val or 0.0)
        except Exception as e:
            log.debug(f"daily pnl lookup failed: {e}")
            return 0.0

    async def _get_strategy_sharpe(self, strategy_id: str) -> float:
        """从 Strategy 表取回测 Sharpe（v2.0: 无回测默认 0，交 risk_engine 门槛拦截）"""
        try:
            async with async_session() as session:
                r = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
                s = r.scalar_one_or_none()
                if s and s.sharpe_ratio:
                    return float(s.sharpe_ratio)
        except Exception as e:
            log.debug(f"strategy sharpe lookup failed: {e}")
        return 0.0

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
        _tick_count = 0
        _last_heartbeat = time.time()
        try:
            while True:
                try:
                    if kill_switch.is_triggered:
                        log.warning(f"StrategyRunner[{sid}]: KILL SWITCH triggered, stopping")
                        break
                    # M4: 续期锁（每个 tick）
                    await self._renew_lock(sid)
                    await self._tick(sid, obj)
                    _tick_count += 1

                    # 心跳日志：每 60 秒输出一次运行状态
                    now = time.time()
                    if now - _last_heartbeat >= 60:
                        pos_qty = self._positions_qty.get(sid, 0.0)
                        pos_usdt = self._positions_usdt.get(sid, 0.0)
                        log.info(
                            f"[RUNNER_HEARTBEAT] sid={sid} symbol={obj.symbol} "
                            f"ticks={_tick_count} uptime={int(now - _last_heartbeat + 60)}s "
                            f"pos_qty={pos_qty:.6f} pos_usdt={pos_usdt:.2f} "
                            f"instance={INSTANCE_ID}"
                        )
                        log_event(sid, "heartbeat",
                                  f"Running: {_tick_count} ticks, pos={pos_qty:.6f} (${pos_usdt:.2f})",
                                  {"ticks": _tick_count, "pos_qty": pos_qty, "pos_usdt": pos_usdt})
                        _last_heartbeat = now

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.error(f"StrategyRunner[{sid}] tick error: {e}")
                    log_event(sid, "error", f"Tick error: {e}", {"error": str(e)})
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            log.info(f"StrategyRunner[{sid}]: stopped (ticks={_tick_count})")
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
                log_event(sid, "stop_loss", f"Stop loss triggered: {result.message}", {
                    "price": current_price, "stop_price": result.stop_price,
                })
                await self._close_position(sid, obj.symbol, sm.side)
                return

        # 3. 分析信号
        signal = await obj.analyze(t)
        if not signal or signal.type == SignalType.HOLD:
            return

        side = "buy" if signal.type in (SignalType.BUY, SignalType.STRONG_BUY) else "sell"
        log_event(sid, f"signal_{side}", f"Signal: {signal.type.value} @ ${current_price:.2f}",
                  {"price": current_price, "signal": signal.type.value})

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

        # 7. risk_engine 全链路检查（v2.0: 真实 daily_pnl + 真实 Sharpe，不再恒 0/1.0）
        sharpe = await self._get_strategy_sharpe(sid)
        daily_pnl = await self._get_daily_pnl()
        # 相关性数据（best-effort：策略池 return_series 为空时 risk_engine 自动跳过）
        strategy_returns = None
        pool_returns = None
        try:
            from services.strategy_pool import strategy_pool
            sp = strategy_pool.get(sid)
            if sp is not None and getattr(sp, "return_series", None):
                strategy_returns = list(sp.return_series)
            entries = getattr(strategy_pool, "_entries", {})
            pool_returns = {
                k: list(v.return_series)
                for k, v in entries.items()
                if getattr(v, "return_series", None)
            }
        except Exception as e:
            log.debug(f"correlation data lookup failed: {e}")

        risk_result = risk_engine.full_check(
            regime=regime,
            strategy_type=strategy_type,
            sharpe_oos=sharpe,
            total_capital=total_capital,
            current_position=current_position,
            new_amount=order_usdt,
            strategy_position=current_position,
            daily_pnl=daily_pnl,
            user_id="system",
            strategy_returns=strategy_returns,
            pool_returns=pool_returns,
        )
        if not risk_result.passed:
            log.info(f"StrategyRunner[{sid}] risk blocked: {risk_result.reason}")
            return

        # 8. 下单 + 对账
        try:
            order = await asyncio.to_thread(
                exmod.shared_exchange.create_market_order, obj.symbol, side, order_amount
            )
            log.info(f"[RUNNER_ORDER] sid={sid} {side} {order_amount:.6f} "
                     f"(@{current_price:.2f} = ${order_usdt:.2f}) id={order.get('id')}")
            log_event(sid, "order_placed",
                      f"{side.upper()} {order_amount:.6f} @ ${current_price:.2f} (≈${order_usdt:.2f})",
                      {"side": side, "amount": order_amount, "price": current_price, "order_id": order.get("id")})

            # 对账（fetch_order 校验订单真实存在）
            if order.get("id"):
                try:
                    verified = await asyncio.to_thread(
                        exmod.shared_exchange.fetch_order, order["id"], obj.symbol
                    )
                    if verified:
                        actual_filled = float(verified.get("filled", 0) or order_amount)
                        actual_cost = float(verified.get("cost", 0) or order_usdt)
                        order_amount = actual_filled
                        order_usdt = actual_cost if actual_cost > 0 else order_usdt
                        log.info(f"[RUNNER_ORDER_VERIFIED] sid={sid} id={order['id']} "
                                 f"filled={actual_filled} cost={actual_cost:.2f}")
                    else:
                        log.warning(f"[RUNNER_ORDER_VERIFY_NULL] sid={sid} id={order['id']}")
                except Exception as e:
                    log.warning(f"[RUNNER_ORDER_VERIFY_FAIL] sid={sid} id={order.get('id')} err={e}")

        except ExchangeError as e:
            log.error(f"StrategyRunner[{sid}] order FAILED: {e}")
            log_event(sid, "order_error", f"Order failed: {e}", {"error": str(e)})
            return
        except Exception as e:
            log.error(f"StrategyRunner[{sid}] order exception: {e}")
            log_event(sid, "order_error", f"Order exception: {e}", {"error": str(e)})
            return

        # v2.0: 审计落库（自动策略订单也走 orders + audit_logs 补偿链）
        try:
            from services.trading_service import record_strategy_order
            await record_strategy_order(sid, obj.symbol, side, order_amount, order, OrderType.MARKET)
        except Exception as e:
            log.warning(f"StrategyRunner[{sid}] strategy order record failed (non-fatal): {e}")

        # 9. 初始化/更新止损状态机（优先使用策略自身风控参数）
        policy = risk_engine.get_policy(regime)
        sl_config = StopLossConfig.from_policy(policy)
        # 策略 config 中的风控参数覆盖全局 policy
        strat_risk = getattr(obj, "config", {}) or {}
        if strat_risk.get("stop_loss_pct"):
            sl_config.stop_loss_pct = float(strat_risk["stop_loss_pct"])
        if strat_risk.get("trailing_stop_pct"):
            sl_config.trailing_stop_pct = float(strat_risk["trailing_stop_pct"])
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
        log.info(f"[RUNNER_POSITION_UPDATE] sid={sid} symbol={obj.symbol} "
                 f"side={side} qty={self._positions_qty[sid]:.6f} "
                 f"usdt={self._positions_usdt[sid]:.2f}")
        await self._persist_state(sid)

    async def _close_position(self, sid: str, symbol: str, side: str):
        """平仓（v2.0: 部分成交时保留剩余仓位）"""
        qty = self._positions_qty.get(sid, 0.0)
        if qty <= 0:
            log.warning(f"[RUNNER_CLOSE_SKIP] sid={sid} qty<=0, nothing to close")
            return
        requested_qty = qty
        entry_usdt = self._positions_usdt.get(sid, 0.0)  # 平仓前已投入资金（算开仓均价）
        close_side = "sell" if side == "long" else "buy"
        log.info(f"[RUNNER_CLOSE_START] sid={sid} symbol={symbol} "
                 f"side={close_side} qty={qty:.6f}")
        try:
            order = await asyncio.to_thread(
                exmod.shared_exchange.create_market_order, symbol, close_side, qty
            )
            log.info(f"[RUNNER_CLOSE_DONE] sid={sid} id={order.get('id')} "
                     f"side={close_side} qty={qty:.6f}")
            log_event(sid, "order_placed",
                      f"CLOSE {close_side.upper()} {qty:.6f} @ market (id={order.get('id')})",
                      {"side": close_side, "amount": qty, "order_id": order.get("id")})

            # 对账
            if order.get("id"):
                try:
                    verified = await asyncio.to_thread(
                        exmod.shared_exchange.fetch_order, order["id"], symbol
                    )
                    if verified:
                        actual_filled = float(verified.get("filled", 0) or qty)
                        qty = actual_filled
                        log.info(f"[RUNNER_CLOSE_VERIFIED] sid={sid} id={order['id']} "
                                 f"filled={actual_filled:.6f}")
                except Exception as e:
                    log.debug(f"Order verification fallback failed for {sid}: {e}")

        except ExchangeError as e:
            log.error(f"[RUNNER_CLOSE_FAILED] sid={sid} error={e}")
            return
        except Exception as e:
            log.error(f"[RUNNER_CLOSE_EXCEPTION] sid={sid} error={e}")
            return

        # v2.0: 审计落库（平仓订单也走 orders + audit_logs 补偿链）
        try:
            from services.trading_service import record_strategy_order
            await record_strategy_order(sid, symbol, close_side, qty, order, OrderType.MARKET)
        except Exception as e:
            log.warning(f"StrategyRunner[{sid}] close order record failed (non-fatal): {e}")

        # v2.0: 记录已平仓交易到 Trade 表（供历史/绩效/日亏损熔断/在线学习数据源）
        await self._record_closed_trade(sid, symbol, side, requested_qty, qty, entry_usdt, order)

        # 清理状态 + 持久化（v2.0: 部分成交时保留剩余仓位，不再整体丢失）
        remaining_qty = requested_qty - qty  # qty 已被 verified 覆盖为实际成交量
        if remaining_qty > 1e-10:
            original_usdt = self._positions_usdt.get(sid, 0.0)
            self._positions_qty[sid] = remaining_qty
            self._positions_usdt[sid] = (
                original_usdt * (remaining_qty / requested_qty) if requested_qty > 0 else 0.0
            )
            log.warning(f"[RUNNER_PARTIAL_CLOSE] sid={sid} symbol={symbol} "
                        f"filled={qty:.6f} remaining={remaining_qty:.6f}")
        else:
            self._stop_managers.pop(sid, None)
            self._positions_usdt.pop(sid, None)
            self._positions_qty.pop(sid, None)
            log.info(f"[RUNNER_POSITION_CLEARED] sid={sid} symbol={symbol}")
        await self._persist_state(sid)

    async def _record_closed_trade(self, sid: str, symbol: str, side: str,
                                   requested_qty: float, filled_qty: float,
                                   entry_usdt: float, order: dict):
        """平仓后记录 Trade（v2.0: 补齐此前缺失的已平仓交易数据源）。

        该数据源是「交易历史/绩效曲线/日亏损熔断/在线学习」的共同基础，
        此前 Trade 表只有读取、从未写入，导致这些功能实际恒为空/恒 0。
        """
        try:
            if filled_qty <= 0 or requested_qty <= 0:
                return
            entry_price = entry_usdt / requested_qty if requested_qty > 0 else 0.0
            exit_price = float(order.get("price") or 0)
            if exit_price <= 0:
                # 市价单 order 可能无 price，用最新价兜底
                try:
                    t = await tick_cache.get(exmod.shared_exchange, symbol)
                    exit_price = float(t.get("last", 0) or 0)
                except Exception:
                    pass
            if entry_price <= 0 or exit_price <= 0:
                return

            if side == "long":
                profit = (exit_price - entry_price) * filled_qty
            else:
                profit = (entry_price - exit_price) * filled_qty
            cost = entry_price * filled_qty
            profit_pct = (profit / cost * 100) if cost > 0 else 0.0

            async with async_session() as session:
                session.add(Trade(
                    strategy_id=sid,
                    symbol=symbol,
                    buy_price=round(entry_price, 6),
                    sell_price=round(exit_price, 6),
                    quantity=filled_qty,
                    profit=round(profit, 4),
                    profit_pct=round(profit_pct, 4),
                    sell_order_id=str(order.get("id") or ""),
                    opened_at=_utcnow_naive(),
                    closed_at=_utcnow_naive(),
                ))
                await session.commit()
            log.info(f"[RUNNER_TRADE_RECORDED] sid={sid} symbol={symbol} "
                     f"entry={entry_price:.6f} exit={exit_price:.6f} profit={profit:.4f}")
        except Exception as e:
            log.warning(f"Runner[{sid}] record closed trade failed (non-fatal): {e}")

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
            "active_symbols": list(set(self._symbol_map.values())),  # U4
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
        from strategies.grid import GridStrategy
        from strategies.ma_cross import MACrossStrategy
        from strategies.rsi_strategy import RSIStrategy
        from strategies.bollinger import BollingerStrategy

        config = strategy.config or {}
        stype = strategy.type

        if stype == StrategyType.GRID:
            # v2.0: 修复 GridStrategy 构造签名不匹配（原传 symbol/lower/upper，实为 strategy_id/name/config）
            return GridStrategy(
                strategy_id=str(strategy.id),
                name=strategy.name,
                config={
                    "symbol": strategy.symbol,
                    "lower_bound": config.get("lower", settings.DEFAULT_GRID_LOWER),
                    "upper_bound": config.get("upper", settings.DEFAULT_GRID_UPPER),
                    "grid_count": config.get("grid_count", settings.DEFAULT_GRID_COUNT),
                },
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
        elif stype in (StrategyType.CUSTOM, StrategyType.ML_SIGNAL, StrategyType.AI_GENERATED):
            # P1-4: CUSTOM/ML_SIGNAL/AI_GENERATED 回退到 CustomStrategy
            from strategies.custom import CustomStrategy
            return CustomStrategy(
                strategy_id=str(strategy.id),
                name=strategy.name,
                config=config,
            )
        else:
            log.warning(f"Runner: cannot build strategy obj for type {stype}, skip")
            return None
    except Exception as e:
        log.error(f"Runner: build_strategy_obj failed for {getattr(strategy, 'id', '?')}: {e}")
        return None


runner = StrategyRunner()
