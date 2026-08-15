"""v2.0 P2: 交易所对账脚本

定时拉取交易所实际持仓/订单，与 DB 记录对比。
差异告警通过 logger 输出，可被 Prometheus + Alertmanager 捕获。

用法:
    python backend/scripts/reconcile.py              # 一次性对账
    python backend/scripts/reconcile.py --daemon 300  # 每 300s 自动运行
"""
import sys
import os
import asyncio
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import log
from core.exchange import shared_exchange  # noqa: E402


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ReconcileResult:
    """对账结果"""

    def __init__(self):
        self.ok = True
        self.issues: list[str] = []
        self.exchange_positions: dict = {}
        self.exchange_orders: list = []
        self.timestamp = _utcnow()

    def add_issue(self, msg: str):
        self.issues.append(msg)
        self.ok = False


async def reconcile(reporter: ReconcileResult | None = None) -> ReconcileResult:
    """执行一次对账"""
    if reporter is None:
        reporter = ReconcileResult()

    # 1. 交易所连通性检查
    ok, msg, _ = shared_exchange.test_connection()
    if not ok:
        reporter.add_issue(f"Exchange offline: {msg}")
        return reporter

    # 2. 拉取交易所合约持仓（v2.0 合约模式：fetch_positions 为真源）
    try:
        positions = shared_exchange.fetch_positions()
        for p in positions:
            sym = p.get("symbol") or ""
            if not sym:
                continue
            coin = sym.split("/")[0]
            reporter.exchange_positions[coin] = p
    except Exception as e:
        reporter.add_issue(f"Fetch positions failed: {e}")

    # 3. 对账: DB positions vs 交易所合约持仓
    try:
        from db.database import async_session
        from db.models import Position
        from sqlalchemy import select

        async with async_session() as session:
            db_positions = (await session.execute(select(Position))).scalars().all()
            db_by_symbol = {p.symbol.split("/")[0]: p for p in db_positions}

            # 交易所有合约持仓但 DB 无记录
            for coin, pos in reporter.exchange_positions.items():
                if coin not in db_by_symbol:
                    reporter.add_issue(
                        f"Contract position in exchange but NOT in DB: {coin} "
                        f"contracts={pos.get('contracts', 0)} side={pos.get('side', '')}"
                    )

            # DB 有持仓但交易所无对应合约持仓
            for p in db_positions:
                coin = p.symbol.split("/")[0]
                if coin not in reporter.exchange_positions and p.quantity > 0:
                    reporter.add_issue(
                        f"Position in DB but NOT in exchange: {p.symbol} qty={p.quantity}"
                    )

    except Exception as e:
        reporter.add_issue(f"DB position comparison failed: {e}")

    # 4. 拉取交易所挂单并对账
    try:
        from db.database import async_session
        from db.models import Order, OrderStatus
        from sqlalchemy import select

        all_orders = []
        for sym in ["BTC/USDT", "ETH/USDT"]:
            try:
                orders = shared_exchange.fetch_open_orders(sym)
                all_orders.extend(orders)
            except Exception:
                pass
        reporter.exchange_orders = all_orders

        async with async_session() as session:
            db_open = (
                await session.execute(
                    select(Order).where(Order.status == OrderStatus.OPEN)
                )
            ).scalars().all()

            exchange_ids = {o.get("id") for o in all_orders}
            for o in db_open:
                if o.exchange_order_id and o.exchange_order_id not in exchange_ids:
                    reporter.add_issue(
                        f"Order in DB (status=OPEN) but NOT in exchange: "
                        f"id={o.id} exchange_id={o.exchange_order_id}"
                    )

    except Exception as e:
        reporter.add_issue(f"Fetch orders failed: {e}")

    return reporter


async def main():
    parser = argparse.ArgumentParser(description="交易所对账脚本")
    parser.add_argument(
        "--daemon", type=int, default=0,
        help="后台模式：每 N 秒运行一次（0=单次运行）",
    )
    args = parser.parse_args()

    if args.daemon > 0:
        log.info(f"Reconcile daemon started, interval={args.daemon}s")
        while True:
            result = await reconcile()
            _report(result)
            if not result.ok:
                log.error(f"RECONCILE FAILED: {len(result.issues)} issues")
                for issue in result.issues:
                    log.error(f"  - {issue}")
            await asyncio.sleep(args.daemon)
    else:
        result = await reconcile()
        _report(result)
        if not result.ok:
            log.error(f"RECONCILE FAILED: {len(result.issues)} issues")
            for issue in result.issues:
                log.error(f"  - {issue}")
            sys.exit(1)
        else:
            log.info("RECONCILE OK: all positions and orders match")


def _report(result: ReconcileResult):
    """输出对账报告"""
    ts = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    status = "OK" if result.ok else "FAILED"
    log.info(f"[{ts}] Reconcile {status} | positions={len(result.exchange_positions)} orders={len(result.exchange_orders)}")
    if result.ok:
        log.info(f"[{ts}] positions={result.exchange_positions}")


if __name__ == "__main__":
    asyncio.run(main())
