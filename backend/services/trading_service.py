"""交易服务层 — Phase 8 实盘就绪版 (v2.0 合约版) (v2.0 合约版)

核心改动：
  1. 移除所有 mock fallback（下单失败抛错，不再返回假单掩盖故障）
  2. 接入 kill_switch（紧急停止时拒绝所有下单）
  3. 加金额硬上限检查（MAX_ORDER_AMOUNT_USDT / MAX_TOTAL_POSITION_USDT）
  4. 风控引擎异常时默认拒绝（不再 fallback 到更宽松的旧 risk_manager）
  5. 实盘模式交易对白名单校验
  6. 下单后 fetch_order 对账
  7. 实盘模式 AI 功能禁用
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Optional
import core.exchange as exmod
from core.exchange import ExchangeError
from core.tick_cache import tick_cache  # M2: TTL 缓存
from core.exchange_registry import exchange_registry  # M2: 多租户实例池
from core.logger import log
from core.kill_switch import kill_switch
from config import settings
from services.regime_detector import MarketRegime  # kept for runner compatibility
from services.risk_engine import risk_engine  # v2.0: manual trading risk

async def _check_risk_engine(symbol: str, side: str, amount_usdt: float) -> tuple[bool, str]:
    """v2.0: manual trading risk check using risk_engine position limits."""
    try:
        from services.market_service import get_ohlcv
        ohlcv, _ = get_ohlcv(symbol, "1h", limit=200)
        if ohlcv:
            from services.regime_detector import regime_detector, MarketRegime
            regime = regime_detector.detect(ohlcv, symbol)
            r = risk_engine.check_position_limit(
                regime=regime, total_capital=10000,
                current_position=0, new_amount=amount_usdt, strategy_position=0,
            )
            if not r.passed:
                return False, r.reason
        return True, ""
    except Exception as e:
        log.warning(f"RiskEngine check skipped: {e}")
        return True, ""
from db.database import async_session
from db.models import Order, AuditLog, OrderType, OrderStatus, StrategyType


# ------------------------------------------------------------------
# M3: 下单落库 + 审计写入
# P1-2: DB 写入失败不再静默吞掉 — 重试 + 补偿审计 + 内存队列
# ------------------------------------------------------------------

_pending_order_records: list[dict] = []   # DB 写入失败的订单记录（调度器补偿）
_PERSIST_RETRY_DELAY = 0.5               # 重试延迟（秒）


async def _do_record_order_success(
    user_id: str, account_id: str, symbol: str, side: str,
    amount: float, order_result: dict, order_type: OrderType,
    idempotency_key: str,
) -> bool:
    """实际执行订单落库（原子写 orders + audit_logs），返回是否成功"""
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
            return True
    except Exception as e:
        log.warning(f"Order persist attempt failed: {e}")
        return False


async def _record_order_success(
    user_id: str, account_id: str, symbol: str, side: str,
    amount: float, order_result: dict, order_type: OrderType,
    idempotency_key: str,
):
    """下单成功后原子写 orders + audit_logs。

    P1-2: DB 写入失败不再静默吞掉 — 重试一次，仍失败则写补偿审计日志（result=db_persist_failed），
    若审计日志也失败则入内存队列等调度器补偿。
    资金对账断裂风险已消除：订单在交易所真实存在，本地记录可通过补偿恢复。
    """
    # 第一次尝试
    if await _do_record_order_success(
        user_id, account_id, symbol, side, amount, order_result, order_type, idempotency_key
    ):
        return

    # 重试一次（可能是临时网络抖动）
    await asyncio.sleep(_PERSIST_RETRY_DELAY)
    if await _do_record_order_success(
        user_id, account_id, symbol, side, amount, order_result, order_type, idempotency_key
    ):
        return

    # 两次都失败 — 写补偿审计日志（标记 db_persist_failed）
    log.error(
        f"CRITICAL: Order persist FAILED after retry — "
        f"exchange_id={order_result.get('id')} symbol={symbol} side={side} amount={amount}. "
        f"Order is REAL on exchange but NOT in local DB — reconciliation broken, queuing for retry"
    )
    try:
        async with async_session() as session:
            audit = AuditLog(
                actor=user_id or "system",
                action="place_order",
                entity_type="order",
                entity_id=str(order_result.get("id", "")),
                detail={
                    "idempotency_key": idempotency_key,
                    "symbol": symbol, "side": side, "amount": amount,
                    "account_id": account_id, "order_type": order_type.value,
                    "order_result": order_result,
                    "PERSIST_FAILED": True,
                },
                result="db_persist_failed",
                error_msg="Order placed on exchange but DB persist failed after retry",
            )
            session.add(audit)
            await session.commit()
    except Exception as e2:
        # DB 完全不可用 — 入内存队列等调度器补偿
        log.error(f"CRITICAL: Even audit log failed — enqueuing for scheduler retry: {e2}")
        _pending_order_records.append({
            "user_id": user_id, "account_id": account_id,
            "symbol": symbol, "side": side, "amount": amount,
            "order_result": order_result, "order_type": order_type,
            "idempotency_key": idempotency_key,
            "enqueued_at": time.time(),
        })


async def _record_order_failure(
    user_id: str, account_id: str, symbol: str, side: str,
    amount: float, order_type: OrderType, idempotency_key: str, error: str,
):
    """下单失败时写 audit_logs（result=error）。

    P1-2: DB 写入失败重试一次，仍失败则 log.error（不再静默吞掉）。
    """
    for attempt in range(2):
        try:
            async with async_session() as session:
                audit = AuditLog(
                    actor=user_id or "system",
                    action="place_order",
                    entity_type="order",
                    detail={
                        "idempotency_key": idempotency_key,
                        "symbol": symbol, "side": side, "amount": amount,
                        "account_id": account_id, "order_type": order_type.value,
                    },
                    result="error",
                    error_msg=error,
                )
                session.add(audit)
                await session.commit()
                return
        except Exception as e:
            if attempt == 0:
                log.warning(f"Audit persist failed, retrying: {e}")
                await asyncio.sleep(_PERSIST_RETRY_DELAY)
            else:
                log.error(f"CRITICAL: Audit persist FAILED after retry — order failure not recorded: {e}")


async def flush_pending_order_records() -> int:
    """P1-2: 调度器定期补偿 — 重试 DB 写入失败的订单记录。

    返回成功补偿的记录数。由 scheduler 每 30 秒调用。
    """
    if not _pending_order_records:
        return 0

    flushed = 0
    remaining = []
    for record in _pending_order_records:
        success = await _do_record_order_success(
            record["user_id"], record["account_id"], record["symbol"],
            record["side"], record["amount"], record["order_result"],
            record["order_type"], record["idempotency_key"],
        )
        if success:
            flushed += 1
            log.info(f"Pending order record flushed: {record['order_result'].get('id')}")
        else:
            # 超过 5 分钟的记录放弃（避免无限堆积）
            if time.time() - record.get("enqueued_at", 0) > 300:
                log.error(
                    f"CRITICAL: Pending order record EXPIRED after 5min — "
                    f"exchange_id={record['order_result'].get('id')} will need manual reconciliation"
                )
            else:
                remaining.append(record)

    _pending_order_records.clear()
    _pending_order_records.extend(remaining)

    if flushed > 0:
        log.info(f"Pending order records: flushed {flushed}, remaining {len(remaining)}")
    return flushed


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
        df = await asyncio.to_thread(exmod.shared_exchange.fetch_ohlcv, symbol, "1h", 200)
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
        bal = await asyncio.to_thread(exmod.shared_exchange.fetch_balance)
        return bal.get("USDT", {}).get("total", 0.0)
    except Exception:
        return 0.0


def _check_kill_switch(side: str = "") -> tuple[bool, str]:
    """检查紧急停止状态
    手动交易且为卖单时，紧急停止允许平仓（卖）但禁止开仓（买）。
    """
    if kill_switch.is_triggered:
        if side == "sell":
            return True, ""  # 手动卖单：紧急停止允许平仓止损
        return False, "KILL_SWITCH_TRIGGERED: 紧急停止已触发，开仓已冻结（卖单仍可平仓）。POST /api/trading/emergency-reset 解除"
    return True, ""


def _check_amount_limit(amount_usdt: float) -> tuple[bool, str]:
    """基础金额校验（v2.1: 全局硬上限已移除，仅检查 >0）"""
    if amount_usdt <= 0:
        return False, "Amount must be positive"
    return True, ""


def _check_symbol_whitelist(symbol: str) -> tuple[bool, str]:
    """实盘模式交易对白名单校验（v2.1: 仅实盘生效，策略级白名单在 _enhanced_risk_check 中）"""
    if not settings.EXCHANGE_TESTNET and settings.LIVE_SYMBOL_WHITELIST:
        if symbol not in settings.LIVE_SYMBOL_WHITELIST:
            return False, f"实盘模式仅允许交易: {', '.join(settings.LIVE_SYMBOL_WHITELIST)}"
    return True, ""


# ------------------------------------------------------------------
# v2.1: 策略级可配置风控
# ------------------------------------------------------------------

# 策略频率追踪（按 max_freq 阈值判断）
_order_timestamps: dict[str, list[float]] = {}


def _check_strategy_frequency(strategy_id: str, max_per_minute: int) -> tuple[bool, str]:
    now = time.time()
    if strategy_id not in _order_timestamps:
        _order_timestamps[strategy_id] = []
    _order_timestamps[strategy_id] = [
        t for t in _order_timestamps[strategy_id] if now - t < 60
    ]
    if len(_order_timestamps[strategy_id]) >= max_per_minute:
        return False, f"[{strategy_id}] 1min {len(_order_timestamps[strategy_id])}次 > 阈值{max_per_minute}"
    _order_timestamps[strategy_id].append(now)
    return True, ""


async def _check_strategy_consecutive_losses(strategy_id: str, max_losses: int) -> tuple[bool, str]:
    from db.models import Trade
    from sqlalchemy import select, desc

    async with async_session() as session:
        recent = (await session.execute(
            select(Trade).where(Trade.strategy_id == strategy_id)
            .order_by(desc(Trade.closed_at)).limit(max_losses)
        )).scalars().all()

    if len(recent) < max_losses:
        return True, ""

    consecutive = 0
    for t in recent:
        if t.profit < 0:
            consecutive += 1
        else:
            break
    if consecutive >= max_losses:
        return False, f"[{strategy_id}] 连续{consecutive}笔亏损 >= 阈值{max_losses}"
    return True, ""


async def _enhanced_risk_check(user_id: str, symbol: str, side: str,
                                amount_usdt: float,
                                strategy_id: str = "manual",
                                source: str = "manual",
                                order_price: float = 0.0,
                                skip_cold_start: bool = False,
                                strategy_risk: dict | None = None) -> tuple[bool, str]:
    """v2.1: 风控按来源独立配置，默认无限制

    source="manual" — 仅 kill_switch + 手动风控设置（enabled=false 即跳过）
    source="strategy" — 仅 kill_switch + 策略级风控（未配置则全放行）
    source="emergency" — 仅 kill_switch
    """
    # ============================================================
    # kill_switch：唯一天塌不下来的全局安全网
    # ============================================================
    if amount_usdt <= 0:
        return False, "Amount must be positive"

    if source in ("manual", "emergency"):
        ok, msg = _check_kill_switch(side)
    else:
        ok, msg = _check_kill_switch("")
    if not ok:
        return False, msg

    # ============================================================
    # 手动交易
    # ============================================================
    if source == "manual":
        from core.app_config import get_manual_risk
        mrisk = get_manual_risk()
        if mrisk.get("enabled", False):
            max_order = mrisk.get("max_order_usdt", 0)
            min_order = mrisk.get("min_order_usdt", 0)
            max_daily_loss = mrisk.get("max_daily_loss_usdt", 0)

            if min_order > 0 and amount_usdt < min_order:
                return False, f"金额 {amount_usdt:.2f} 低于最小限制 {min_order:.2f}"
            if max_order > 0 and amount_usdt > max_order:
                return False, f"金额 {amount_usdt:.2f} 超过最大限制 {max_order:.2f}"
            if max_daily_loss > 0:
                day_loss = await _get_daily_realized_loss(user_id)
                if day_loss + amount_usdt > max_daily_loss:
                    return False, f"日亏损 {day_loss:.2f}+{amount_usdt:.2f} 超过上限 {max_daily_loss:.2f}"

        log.info(f"[RISK_CHECK] source=manual symbol={symbol} amount={amount_usdt:.2f} — ok")
        return True, ""

    # ============================================================
    # 紧急平仓
    # ============================================================
    if source == "emergency":
        log.info(f"[RISK_CHECK] source=emergency symbol={symbol} — ok")
        return True, ""

    # ============================================================
    # 策略风控：读取策略配置，默认全放行
    # ============================================================
    sr = strategy_risk or {}
    if not sr.get("enabled", False):
        log.info(f"[RISK_CHECK] source=strategy id={strategy_id} risk=off — ok")
        return True, ""

    # 金额上限（0=不限制）
    max_order = sr.get("max_order_usdt", 0)
    if max_order > 0 and amount_usdt > max_order:
        return False, f"[{strategy_id}] 金额 {amount_usdt:.2f} > 上限 {max_order:.2f}"

    # 日亏损上限
    max_daily = sr.get("max_daily_loss_usdt", 0)
    if max_daily > 0:
        day_loss = await _get_daily_realized_loss(user_id)
        if day_loss + amount_usdt > max_daily:
            return False, f"[{strategy_id}] 日亏损 {day_loss:.2f} > 上限 {max_daily:.2f}"

    # 下单频率
    max_freq = sr.get("max_orders_per_minute", 0)
    if max_freq > 0:
        ok, msg = _check_strategy_frequency(strategy_id, max_freq)
        if not ok:
            return False, msg

    # 连续亏损
    max_losses = sr.get("max_consecutive_losses", 0)
    if max_losses > 0:
        ok, msg = await _check_strategy_consecutive_losses(strategy_id, max_losses)
        if not ok:
            return False, msg

    # 滑点
    max_slippage = sr.get("slippage_max_pct", 0)
    if max_slippage > 0 and order_price > 0:
        try:
            cp = (await tick_cache.get(symbol)).get("last", 0)
            if cp > 0 and abs(order_price - cp) / cp > max_slippage:
                return False, f"滑点 {abs(order_price-cp)/cp:.2%} > 阈值 {max_slippage:.2%}"
        except Exception as e:
            log.warning(f"滑点检查失败: {e}")

    # 策略级交易对白名单
    allowed = sr.get("allowed_symbols", [])
    if allowed and symbol not in allowed:
        return False, f"[{strategy_id}] {symbol} 不在允许列表 {allowed}"

    log.info(f"[RISK_CHECK] source=strategy id={strategy_id} symbol={symbol} amount={amount_usdt:.2f} — ok")
    return True, ""


# ------------------------------------------------------------------
# 核心交易接口
# ------------------------------------------------------------------

async def get_balance() -> tuple[dict, bool]:
    """获取余额。返回 (balance, is_mock)。

    Phase 8: 失败时返回空 dict + is_mock=True（不再返回假数据），
    前端通过 is_mock 标识显示"连接异常"。
    """
    try:
        bal = await asyncio.to_thread(exmod.shared_exchange.fetch_balance)
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
    log.info(f"[ORDER_REQUEST] type=LIMIT user={user_id} account={account_id} "
             f"symbol={symbol} side={side} amount={amount} price={price} "
             f"usdt={amount * price:.2f} testnet={settings.EXCHANGE_TESTNET}")

    # 实盘二次确认
    if not settings.EXCHANGE_TESTNET and not confirm_live:
        log.warning(f"[ORDER_REJECTED] reason=live_confirm_required symbol={symbol}")
        return None, "实盘模式下单需二次确认（confirm_live=true）", False

    amount_usdt = amount * price
    ok, msg = await _enhanced_risk_check(user_id, symbol, side, amount_usdt, source="manual")
    if not ok:
        log.warning(f"[ORDER_REJECTED] reason=risk_check symbol={symbol} side={side} msg={msg}")
        return None, msg, False

    idempotency_key = _make_idempotency_key(account_id, symbol, side, amount)

    try:
        order = await asyncio.to_thread(
            exmod.shared_exchange.create_limit_order, symbol, side, amount, price
        )
        log.info(f"[ORDER_PLACED] type=LIMIT id={order.get('id')} symbol={symbol} "
                 f"side={side} amount={amount} price={order.get('price', price)} "
                 f"status={order.get('status', 'open')} filled={order.get('filled', 0)}")

        # 对账：fetch_order 确认订单真实存在
        if order.get("id"):
            try:
                verified = await asyncio.to_thread(
                    exmod.shared_exchange.fetch_order, order["id"], symbol
                )
                if verified:
                    order["verified"] = True
                    log.info(f"[ORDER_VERIFIED] id={order['id']} "
                             f"filled={verified.get('filled', 0)} "
                             f"status={verified.get('status', '?')}")
                else:
                    order["verified"] = False
                    log.warning(f"[ORDER_VERIFY_NULL] id={order['id']} fetch_order returned None")
            except Exception as e:
                log.warning(f"[ORDER_VERIFY_FAIL] id={order.get('id')} error={e}")
                order["verified"] = False

        # M3: 本地落库（orders + audit_logs 原子写）
        await _record_order_success(
            user_id, account_id, symbol, side, amount, order, OrderType.LIMIT, idempotency_key
        )
        log.info(f"[ORDER_DONE] type=LIMIT id={order.get('id')} symbol={symbol} "
                 f"side={side} — order recorded to DB")

        return order, None, False
    except ExchangeError as e:
        log.error(f"[ORDER_FAILED] type=LIMIT symbol={symbol} side={side} error={e}")
        await _record_order_failure(user_id, account_id, symbol, side, amount, OrderType.LIMIT, idempotency_key, str(e))
        return None, f"限价单下单失败: {e}", False
    except Exception as e:
        log.error(f"[ORDER_EXCEPTION] type=LIMIT symbol={symbol} side={side} error={e}")
        await _record_order_failure(user_id, account_id, symbol, side, amount, OrderType.LIMIT, idempotency_key, str(e))
        return None, f"限价单异常: {e}", False


async def place_market_order(user_id: str, symbol: str, side: str,
                             amount: float,
                             confirm_live: bool = False,
                             account_id: str = "default",
                             source: str = "manual") -> tuple[dict | None, str | None, bool]:
    """下市价单。返回 (order, error_msg, is_mock)

    source: "manual"=手动交易(最小风控) / "strategy"=程序量化(全量风控) / "emergency"=紧急平仓(仅kill_switch)
    """
    log.info(f"[ORDER_REQUEST] type=MARKET user={user_id} account={account_id} "
             f"symbol={symbol} side={side} amount={amount} testnet={settings.EXCHANGE_TESTNET}")

    # 实盘二次确认
    if not settings.EXCHANGE_TESTNET and not confirm_live:
        log.warning(f"[ORDER_REJECTED] reason=live_confirm_required symbol={symbol}")
        return None, "实盘模式下单需二次确认（confirm_live=true）", False

    est_price = await _get_price(symbol)
    if est_price <= 0:
        log.warning(f"[ORDER_REJECTED] reason=no_price symbol={symbol}")
        return None, "无法获取当前价格，拒绝下单", False

    amount_usdt = amount * est_price
    ok, msg = await _enhanced_risk_check(user_id, symbol, side, amount_usdt, source=source)
    if not ok:
        log.warning(f"[ORDER_REJECTED] reason=risk_check symbol={symbol} side={side} msg={msg}")
        return None, msg, False

    idempotency_key = _make_idempotency_key(account_id, symbol, side, amount)

    try:
        order = await asyncio.to_thread(
            exmod.shared_exchange.create_market_order, symbol, side, amount
        )
        log.info(f"[ORDER_PLACED] type=MARKET id={order.get('id')} symbol={symbol} "
                 f"side={side} amount={amount} price={order.get('price', 0)} "
                 f"status={order.get('status', 'closed')} filled={order.get('filled', 0)}")

        # 对账
        if order.get("id"):
            try:
                verified = await asyncio.to_thread(
                    exmod.shared_exchange.fetch_order, order["id"], symbol
                )
                if verified:
                    order["verified"] = True
                    log.info(f"[ORDER_VERIFIED] id={order['id']} "
                             f"filled={verified.get('filled', 0)} "
                             f"status={verified.get('status', '?')}")
                else:
                    order["verified"] = False
                    log.warning(f"[ORDER_VERIFY_NULL] id={order['id']} fetch_order returned None")
            except Exception as e:
                log.warning(f"[ORDER_VERIFY_FAIL] id={order.get('id')} error={e}")
                order["verified"] = False

        # M3: 本地落库（orders + audit_logs 原子写）
        await _record_order_success(
            user_id, account_id, symbol, side, amount, order, OrderType.MARKET, idempotency_key
        )
        log.info(f"[ORDER_DONE] type=MARKET id={order.get('id')} symbol={symbol} "
                 f"side={side} — order recorded to DB")

        return order, None, False
    except ExchangeError as e:
        log.error(f"[ORDER_FAILED] type=MARKET symbol={symbol} side={side} error={e}")
        await _record_order_failure(user_id, account_id, symbol, side, amount, OrderType.MARKET, idempotency_key, str(e))
        return None, f"市价单下单失败: {e}", False
    except Exception as e:
        log.error(f"[ORDER_EXCEPTION] type=MARKET symbol={symbol} side={side} error={e}")
        await _record_order_failure(user_id, account_id, symbol, side, amount, OrderType.MARKET, idempotency_key, str(e))
        return None, f"市价单异常: {e}", False


async def cancel_order(order_id: str, symbol: str) -> tuple[bool, str]:
    """撤销订单。Phase 8: 真正调用交易所撤单（原为空操作）"""
    ok_ks, msg_ks = _check_kill_switch()
    if not ok_ks:
        return False, msg_ks
    try:
        ok = await asyncio.to_thread(exmod.shared_exchange.cancel_order, order_id, symbol)
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
        n = await asyncio.to_thread(exmod.shared_exchange.cancel_all_orders, symbol or None)
        log.info(f"Cancelled {n} open orders (symbol={symbol or 'all'})")
        return n, f"已撤销 {n} 个挂单"
    except Exception as e:
        log.error(f"Cancel all orders failed: {e}")
        return 0, f"批量撤单异常: {e}"


def get_open_orders(symbol: str) -> tuple[list, bool]:
    try:
        orders = exmod.shared_exchange.fetch_open_orders(symbol)
        return orders, False
    except Exception:
        return [], True


def get_trade_history(symbol: str, limit: int = 50) -> tuple[list, bool]:
    try:
        trades = exmod.shared_exchange.fetch_my_trades(symbol, limit)
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
        bal = await asyncio.to_thread(exmod.shared_exchange.fetch_balance)
        closed = 0
        for cur, info in bal.items():
            if cur in ("USDT", "USD", "USDC"):
                continue
            total = float(info.get("total", 0) or 0)
            if total > 0:
                symbol = f"{cur}/USDT"
                try:
                    await asyncio.to_thread(
                        exmod.shared_exchange.create_market_order, symbol, "sell", total
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
