"""对账服务 — 交易所实际持仓/订单 vs 本地状态（v6 收敛期）

真源对齐：合约模式下本地真源是 runner 的内存持仓（RunnerState 落库），
交易所真源是 fetch_positions()。两者不一致时必须告警，避免「本地以为有仓
但交易所没有」或「交易所有仓但本地不知情」导致的重复开仓/漏平。

v6 修正：原 scripts/reconcile.py 误用废弃的 Position 表对账，本服务改为
runner._positions_qty / _positions_usdt + Strategy.symbol 映射，并按名义价值
(USDT) 对比，规避「张数 vs 币数量」的单位差异。
"""
from datetime import datetime, timezone
from core.logger import log
from core.exchange import shared_exchange


class ReconcileResult:
    """对账结果"""

    def __init__(self):
        self.ok = True
        self.issues: list[str] = []
        self.exchange_positions: list[dict] = []
        self.exchange_orders: list[dict] = []
        self.timestamp = datetime.now(timezone.utc).replace(tzinfo=None)

    def add_issue(self, msg: str):
        self.issues.append(msg)
        self.ok = False


async def reconcile() -> ReconcileResult:
    """执行一次对账（持仓 + 挂单）。返回 ReconcileResult。"""
    result = ReconcileResult()

    # 1. 交易所连通性
    ok, _msg, _ = shared_exchange.test_connection()
    if not ok:
        result.add_issue(f"Exchange offline: {_msg}")
        return result

    # 2. 交易所合约持仓（真源）
    try:
        result.exchange_positions = shared_exchange.fetch_positions()
    except Exception as e:
        result.add_issue(f"Fetch positions failed: {e}")

    # 3. 本地持仓（runner 内存真源）
    from strategies.runner import runner
    local_qty = {k: v for k, v in runner._positions_qty.items() if v > 0}
    local_usdt = {k: v for k, v in runner._positions_usdt.items() if v > 0}

    # 4. sid → symbol 映射（runner 内存映射优先，DB 兜底）
    sid_symbol: dict[str, str] = dict(runner._symbol_map)
    try:
        from db.database import async_session
        from db.models import Strategy
        from sqlalchemy import select
        async with async_session() as session:
            rows = (await session.execute(select(Strategy.id, Strategy.symbol))).all()
            for sid, sym in rows:
                sid_symbol.setdefault(sid, sym)
    except Exception as e:
        log.warning(f"Reconcile: strategy symbol map load failed: {e}")

    # 5. 按 symbol 汇总本地名义价值（USDT）
    local_usdt_by_symbol: dict[str, float] = {}
    for sid, usdt in local_usdt.items():
        sym = sid_symbol.get(sid)
        if sym:
            local_usdt_by_symbol[sym] = local_usdt_by_symbol.get(sym, 0.0) + usdt

    # 6. 交易所按 symbol 汇总名义价值
    exch_by_symbol: dict[str, float] = {}
    for p in result.exchange_positions:
        sym = p.get("symbol") or ""
        if not sym:
            continue
        notional = float(p.get("notional", 0) or 0)
        if notional <= 0:
            # notional 缺失时用 张数×contractSize×mark 兜底
            notional = float(p.get("contracts", 0) or 0) * float(
                shared_exchange.get_contract_size(sym)
            ) * float(p.get("mark_price", 0) or 0)
        exch_by_symbol[sym] = exch_by_symbol.get(sym, 0.0) + notional

    # 7. 持仓对比（名义价值差异 > 2 USDT 视为不一致）
    _NOTIONAL_TOLERANCE = 2.0
    all_symbols = set(local_usdt_by_symbol) | set(exch_by_symbol)
    for sym in sorted(all_symbols):
        local = local_usdt_by_symbol.get(sym, 0.0)
        exch = exch_by_symbol.get(sym, 0.0)
        if local <= 0 < exch:
            result.add_issue(f"交易所 {sym} 有持仓(${exch:.2f})但本地无记录")
        elif exch <= 0 < local:
            result.add_issue(f"本地 {sym} 有持仓(${local:.2f})但交易所无对应持仓")
        elif abs(local - exch) > _NOTIONAL_TOLERANCE:
            result.add_issue(
                f"持仓名义价值不一致 {sym}: 本地=${local:.2f} vs 交易所=${exch:.2f}"
            )

    # 8. 挂单对账（DB status=OPEN vs 交易所 open orders）
    await _reconcile_open_orders(result)

    return result


async def _reconcile_open_orders(result: ReconcileResult):
    """DB 中 status=OPEN 的订单若在交易所不存在 → 差异"""
    try:
        from db.database import async_session
        from db.models import Order, OrderStatus
        from sqlalchemy import select

        all_orders: list[dict] = []
        for sym in ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]:
            try:
                all_orders.extend(shared_exchange.fetch_open_orders(sym))
            except Exception:
                pass
        result.exchange_orders = all_orders

        async with async_session() as session:
            db_open = (
                await session.execute(
                    select(Order).where(Order.status == OrderStatus.OPEN)
                )
            ).scalars().all()

        exchange_ids = {o.get("id") for o in all_orders if o.get("id")}
        for o in db_open:
            if o.exchange_order_id and o.exchange_order_id not in exchange_ids:
                result.add_issue(
                    f"本地挂单(OPEN)但交易所不存在: id={o.id} "
                    f"exchange_id={o.exchange_order_id}"
                )
    except Exception as e:
        result.add_issue(f"Open order reconcile failed: {e}")


async def reconcile_and_alert() -> ReconcileResult:
    """对账 + 差异告警（供调度器定时调用）。"""
    result = await reconcile()
    if not result.ok:
        log.error(f"RECONCILE FAILED: {len(result.issues)} issues")
        for issue in result.issues:
            log.error(f"  - {issue}")
        try:
            from services.alert_service import alert_service
            await alert_service.reconcile_mismatch(result.issues)
        except Exception as e:
            log.warning(f"Reconcile alert failed: {e}")
    else:
        log.info(
            f"RECONCILE OK: positions={len(result.exchange_positions)} "
            f"orders={len(result.exchange_orders)}"
        )
    return result
