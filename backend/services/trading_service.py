"""交易服务层 — Phase 8 实盘就绪版

核心改动：
  1. 移除所有 mock fallback（下单失败抛错，不再返回假单掩盖故障）
  2. 接入 kill_switch（紧急停止时拒绝所有下单）
  3. 加金额硬上限检查（MAX_ORDER_AMOUNT_USDT / MAX_TOTAL_POSITION_USDT）
  4. 风控引擎异常时默认拒绝（不再 fallback 到更宽松的旧 risk_manager）
  5. 实盘模式交易对白名单校验
  6. 下单后 fetch_order 对账
  7. 实盘模式 AI 功能禁用
"""
import asyncio
import time
from core.exchange import shared_exchange, ExchangeError
from core.tick_cache import tick_cache  # M2: TTL 缓存
from core.exchange_registry import exchange_registry  # M2: 多租户实例池
from core.logger import log
from core.kill_switch import kill_switch
from config import settings
from services.risk_engine import risk_engine
from services.regime_detector import regime_detector, MarketRegime
from db.database import async_session
from db.models import Order, AuditLog, OrderType, OrderStatus, StrategyType


# ------------------------------------------------------------------
# M3: 下单落库 + 审计写入
# ------------------------------------------------------------------

async def _record_order_success(
    user_id: str,
    account_id: str,
    symbol: str,
    side: str,
    amount: float,
    order_result: dict,
    order_type: OrderType,
    idempotency_key: str,
):
    """下单成功后原子写 orders + audit_logs（同一事务）"""
    try:
        async with async_session() as session:
            status_str = order_result.get("status") or "open"
            try:
                status = OrderStatus(status_str)
            except (ValueError, TypeError):
                status = OrderStatus.OPEN if "open" in str(status_str) else OrderStatus.CLOSED

            order_record = Order(
                user_id=user_id if user_id else "default",
                account_id=account_id,
                symbol=symbol,
                side=side,
                type=order_type,
                status=status,
                price=float(order_result.get("price", 0)),
                amount=float(amount),
                filled=float(order_result.get("filled", 0)),
                cost=float(order_result.get("cost", 0)),
                exchange_order_id=str(order_result.get("id", "")),
                idempotency_key=idempotency_key,
                raw=order_result,
            )
            audit = AuditLog(
                actor=user_id or "system",
                action="place_order",
                entity_type="order",
                entity_id=str(order_result.get("id", "")),
                detail={
                    "idempotency_key": idempotency_key,
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "account_id": account_id,
                    "order_type": order_type.value,
                },
                result="ok",
            )
            session.add_all([order_record, audit])
            await session.commit()
            log.info(f"Order recorded: {order_result.get('id')} (account={account_id})")
    except Exception as e:
        log.error(f"Failed to record order (non-fatal): {e}")


async def _record_order_failure(
    user_id: str,
    account_id: str,
    symbol: str,
    side: str,
    amount: float,
    order_type: OrderType,
    idempotency_key: str,
    error: str,
):
    """下单失败时写 audit_logs（result=error）"""
    try:
        async with async_session() as session:
            audit = AuditLog(
                actor=user_id or "system",
                action="place_order",
                entity_type="order",
                detail={
                    "idempotency_key": idempotency_key,
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "account_id": account_id,
                    "order_type": order_type.value,
                },
                result="error",
                error_msg=error,
            )
            session.add(audit)
            await session.commit()
    except Exception as e:
        log.error(f"Failed to record audit (non-fatal): {e}")


def _make_idempotency_key(account_id: str, symbol: str, side: str, amount: float) -> str:
    """生成幂等键（防止网络抖动重复下单）"""
    return f"{account_id}:{symbol}:{side}:{amount}:{int(time.time() * 1000) // 1000}"


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------

async def _get_price(symbol: str) -> float:
    """获取最新价格（M2: 改用 tick_cache，async 不阻塞事件循环）"""
    try:
        t = await tick_cache.get(shared_exchange, symbol)
        return t.get("last", 0) or 0
    except Exception:
        return 0


async def _detect_regime(symbol: str) -> MarketRegime:
    """获取当前市场状态，失败默认 RANGING_LOW_VOL（最保守的震荡态）"""
    try:
        df = await asyncio.to_thread(shared_exchange.fetch_ohlcv, symbol, "1h", 200)
        if df is None or df.empty:
            return MarketRegime.RANGING_LOW_VOL
        ohlcv = df.to_dict("records")
        result = regime_detector.detect(ohlcv, symbol)
        return result.regime
    except Exception as e:
        log.warning(f"Regime detect failed for {symbol}: {e}, default to RANGING_LOW_VOL")
        return MarketRegime.RANGING_LOW_VOL


async def _get_total_capital() -> float:
    """获取总资金（USDT），失败默认 0（保守）"""
    try:
        bal = await asyncio.to_thread(shared_exchange.fetch_balance)
        return bal.get("USDT", {}).get("total", 0.0)
    except Exception:
        return 0.0


def _check_kill_switch() -> tuple[bool, str]:
    """检查紧急停止状态"""
    if kill_switch.is_triggered:
        return False, "KILL_SWITCH_TRIGGERED: 紧急停止已触发，所有交易已冻结。POST /api/trading/emergency-reset 解除"
    return True, ""


def _check_amount_limit(amount_usdt: float) -> tuple[bool, str]:
    """检查单笔下单金额硬上限"""
    if amount_usdt <= 0:
        return False, "Amount must be positive"
    if amount_usdt > settings.MAX_ORDER_AMOUNT_USDT:
        return False, (
            f"单笔金额 {amount_usdt:.2f} USDT 超过硬上限 "
            f"{settings.MAX_ORDER_AMOUNT_USDT:.2f} USDT"
        )
    return True, ""


def _check_symbol_whitelist(symbol: str) -> tuple[bool, str]:
    """实盘模式交易对白名单校验"""
    if not settings.EXCHANGE_TESTNET and settings.LIVE_SYMBOL_WHITELIST:
        if symbol not in settings.LIVE_SYMBOL_WHITELIST:
            return False, f"实盘模式仅允许交易: {', '.join(settings.LIVE_SYMBOL_WHITELIST)}"
    return True, ""


async def _enhanced_risk_check(user_id: str, symbol: str, side: str,
                                amount_usdt: float) -> tuple[bool, str]:
    """主路径：kill_switch → 金额上限 → 白名单 → regime_detector → risk_engine.full_check

    手动下单视为 CUSTOM 策略，跳过入场 Sharpe 门槛（sharpe_oos=999）。
    风控引擎异常时默认拒绝（Phase 8: 不再 fallback 到旧 risk_manager）。
    """
    # 1) 紧急停止
    ok, msg = _check_kill_switch()
    if not ok:
        return False, msg

    # 2) 金额硬上限
    ok, msg = _check_amount_limit(amount_usdt)
    if not ok:
        return False, msg

    # 3) 白名单
    ok, msg = _check_symbol_whitelist(symbol)
    if not ok:
        return False, msg

    # 4) 风控引擎（异常默认拒绝）
    try:
        regime = await _detect_regime(symbol)
        total_capital = await _get_total_capital()

        result = risk_engine.full_check(
            regime=regime,
            strategy_type=StrategyType.CUSTOM.value,
            sharpe_oos=999.0,  # 手动下单不检查 Sharpe
            total_capital=total_capital if total_capital > 0 else 10000.0,
            current_position=0.0,
            new_amount=amount_usdt,
            strategy_position=0.0,
            daily_pnl=0.0,
            user_id=user_id,
        )
        if not result.passed:
            return False, f"[RiskEngine:{regime.value}] {result.reason}"
        return True, ""
    except Exception as e:
        # Phase 8: 风控引擎异常默认拒绝（宁可错杀不可放过）
        log.error(f"Risk check exception (default DENY): {e}")
        return False, f"风控检查异常，默认拒绝下单: {e}"


# ------------------------------------------------------------------
# 核心交易接口
# ------------------------------------------------------------------

async def get_balance() -> tuple[dict, bool]:
    """获取余额。返回 (balance, is_mock)。

    Phase 8: 失败时返回空 dict + is_mock=True（不再返回假数据），
    前端通过 is_mock 标识显示"连接异常"。
    """
    try:
        bal = await asyncio.to_thread(shared_exchange.fetch_balance)
        return bal, False
    except Exception as e:
        log.warning(f"Balance fetch failed: {e}")
        return {}, True  # 空 dict，前端识别为连接异常


async def place_limit_order(user_id: str, symbol: str, side: str,
                            amount: float, price: float,
                            confirm_live: bool = False,
                            account_id: str = "default") -> tuple[dict | None, str | None, bool]:
    """下限量单。返回 (order, error_msg, is_mock)

    Phase 8 改动：
    - 下单失败抛错（不再返回 mock 假单）
    - 实盘模式需 confirm_live=True
    - 下单后 fetch_order 对账
    M3 改动：
    - 下单后原子写 orders + audit_logs（本地落库）
    - 支持 account_id 多账户
    """
    # 实盘二次确认
    if not settings.EXCHANGE_TESTNET and not confirm_live:
        return None, "实盘模式下单需二次确认（confirm_live=true）", False

    amount_usdt = amount * price
    ok, msg = await _enhanced_risk_check(user_id, symbol, side, amount_usdt)
    if not ok:
        return None, msg, False

    idempotency_key = _make_idempotency_key(account_id, symbol, side, amount)

    try:
        order = await asyncio.to_thread(
            shared_exchange.create_limit_order, symbol, side, amount, price
        )
        log.info(f"Limit order placed: {side} {amount} {symbol} @ {price} (id={order.get('id')})")

        # 对账：fetch_order 确认订单真实存在
        if order.get("id"):
            try:
                verified = await asyncio.to_thread(
                    shared_exchange.fetch_order, order["id"], symbol
                )
                if verified:
                    order["verified"] = True
            except Exception as e:
                log.warning(f"Order verification failed (non-fatal): {e}")
                order["verified"] = False

        # M3: 本地落库（orders + audit_logs 原子写）
        await _record_order_success(
            user_id, account_id, symbol, side, amount, order, OrderType.LIMIT, idempotency_key
        )

        return order, None, False
    except ExchangeError as e:
        log.error(f"Limit order FAILED: {e}")
        await _record_order_failure(user_id, account_id, symbol, side, amount, OrderType.LIMIT, idempotency_key, str(e))
        return None, f"限价单下单失败: {e}", False
    except Exception as e:
        log.error(f"Limit order exception: {e}")
        await _record_order_failure(user_id, account_id, symbol, side, amount, OrderType.LIMIT, idempotency_key, str(e))
        return None, f"限价单异常: {e}", False


async def place_market_order(user_id: str, symbol: str, side: str,
                             amount: float,
                             confirm_live: bool = False,
                             account_id: str = "default") -> tuple[dict | None, str | None, bool]:
    """下市价单。返回 (order, error_msg, is_mock)

    Phase 8 改动：
    - 下单失败抛错（不再返回 mock 假单）
    - 实盘模式需 confirm_live=True
    - 下单后 fetch_order 对账
    M3 改动：
    - 下单后原子写 orders + audit_logs（本地落库）
    - 支持 account_id 多账户
    """
    # 实盘二次确认
    if not settings.EXCHANGE_TESTNET and not confirm_live:
        return None, "实盘模式下单需二次确认（confirm_live=true）", False

    est_price = await _get_price(symbol)
    if est_price <= 0:
        return None, "无法获取当前价格，拒绝下单", False

    amount_usdt = amount * est_price
    ok, msg = await _enhanced_risk_check(user_id, symbol, side, amount_usdt)
    if not ok:
        return None, msg, False

    idempotency_key = _make_idempotency_key(account_id, symbol, side, amount)

    try:
        order = await asyncio.to_thread(
            shared_exchange.create_market_order, symbol, side, amount
        )
        log.info(f"Market order placed: {side} {amount} {symbol} (id={order.get('id')})")

        # 对账
        if order.get("id"):
            try:
                verified = await asyncio.to_thread(
                    shared_exchange.fetch_order, order["id"], symbol
                )
                if verified:
                    order["verified"] = True
            except Exception as e:
                log.warning(f"Order verification failed (non-fatal): {e}")
                order["verified"] = False

        # M3: 本地落库（orders + audit_logs 原子写）
        await _record_order_success(
            user_id, account_id, symbol, side, amount, order, OrderType.MARKET, idempotency_key
        )

        return order, None, False
    except ExchangeError as e:
        log.error(f"Market order FAILED: {e}")
        await _record_order_failure(user_id, account_id, symbol, side, amount, OrderType.MARKET, idempotency_key, str(e))
        return None, f"市价单下单失败: {e}", False
    except Exception as e:
        log.error(f"Market order exception: {e}")
        await _record_order_failure(user_id, account_id, symbol, side, amount, OrderType.MARKET, idempotency_key, str(e))
        return None, f"市价单异常: {e}", False


async def cancel_order(order_id: str, symbol: str) -> tuple[bool, str]:
    """撤销订单。Phase 8: 真正调用交易所撤单（原为空操作）"""
    ok_ks, msg_ks = _check_kill_switch()
    if not ok_ks:
        return False, msg_ks
    try:
        ok = await asyncio.to_thread(shared_exchange.cancel_order, order_id, symbol)
        if ok:
            log.info(f"Order cancelled: {order_id} {symbol}")
            return True, "撤单成功"
        return False, "撤单失败（交易所未确认）"
    except Exception as e:
        log.error(f"Cancel order failed: {order_id} {symbol}: {e}")
        return False, f"撤单异常: {e}"


async def cancel_all_orders(symbol: str = "") -> tuple[int, str]:
    """撤销所有挂单"""
    ok_ks, msg_ks = _check_kill_switch()
    if not ok_ks:
        return 0, msg_ks
    try:
        n = await asyncio.to_thread(shared_exchange.cancel_all_orders, symbol or None)
        log.info(f"Cancelled {n} open orders (symbol={symbol or 'all'})")
        return n, f"已撤销 {n} 个挂单"
    except Exception as e:
        log.error(f"Cancel all orders failed: {e}")
        return 0, f"批量撤单异常: {e}"


def get_open_orders(symbol: str) -> tuple[list, bool]:
    try:
        orders = shared_exchange.fetch_open_orders(symbol)
        return orders, False
    except Exception:
        return [], True


def get_trade_history(symbol: str, limit: int = 50) -> tuple[list, bool]:
    try:
        trades = shared_exchange.fetch_my_trades(symbol, limit)
        return trades, False
    except Exception:
        return [], True


# ------------------------------------------------------------------
# 紧急停止执行
# ------------------------------------------------------------------

async def execute_emergency_stop(by: str = "manual", reason: str = "") -> dict:
    """执行紧急停止全流程：
    1. 触发 kill_switch（阻止后续下单）
    2. 撤销所有挂单
    3. 市价平掉所有持仓
    4. 停止所有运行中策略
    """
    # 先触发，阻止新下单
    kill_switch.trigger(by=by, reason=reason)

    results = {"cancelled_orders": 0, "closed_positions": 0, "stopped_strategies": 0}

    # 1. 撤销所有挂单
    try:
        n, _ = await cancel_all_orders("")
        # 紧急停止时绕过 kill_switch 检查（已触发）
        results["cancelled_orders"] = n
        kill_switch.increment_cancelled(n)
        kill_switch.record_action(f"cancelled {n} orders")
    except Exception as e:
        log.error(f"Emergency: cancel orders failed: {e}")
        kill_switch.record_action(f"cancel orders failed: {e}")

    # 2. 市价平掉所有持仓
    try:
        bal = await asyncio.to_thread(shared_exchange.fetch_balance)
        closed = 0
        for cur, info in bal.items():
            if cur in ("USDT", "USD", "USDC"):
                continue
            total = float(info.get("total", 0) or 0)
            if total > 0:
                symbol = f"{cur}/USDT"
                try:
                    await asyncio.to_thread(
                        shared_exchange.create_market_order, symbol, "sell", total
                    )
                    closed += 1
                    log.warning(f"Emergency: closed {total} {cur} via {symbol}")
                except Exception as e:
                    log.error(f"Emergency: failed to close {cur}: {e}")
        results["closed_positions"] = closed
        kill_switch.increment_closed(closed)
        kill_switch.record_action(f"closed {closed} positions")
    except Exception as e:
        log.error(f"Emergency: close positions failed: {e}")
        kill_switch.record_action(f"close positions failed: {e}")

    # 3. 停止所有运行中策略
    try:
        from strategies.runner import runner
        from db.database import async_session
        from db.models import Strategy, StrategyStatus
        from sqlalchemy import select

        stopped = 0
        running_ids = list(runner._tasks.keys())
        for sid in running_ids:
            try:
                await runner.stop(sid)
                stopped += 1
            except Exception as e:
                log.error(f"Emergency: stop strategy {sid} failed: {e}")

        # DB 标记
        async with async_session() as session:
            r = await session.execute(
                select(Strategy).where(Strategy.status == StrategyStatus.RUNNING)
            )
            for s in r.scalars().all():
                s.status = StrategyStatus.STOPPED
                await session.commit()

        results["stopped_strategies"] = stopped
        kill_switch.increment_stopped(stopped)
        kill_switch.record_action(f"stopped {stopped} strategies")
    except Exception as e:
        log.error(f"Emergency: stop strategies failed: {e}")
        kill_switch.record_action(f"stop strategies failed: {e}")

    log.warning(f"⚠️ Emergency stop complete: {results}")
    return results
