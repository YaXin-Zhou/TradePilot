"""v2.0 P2: 交易所对账脚本（CLI 薄封装）

对账逻辑已迁至 services/reconcile_service.py（v6 修正为 RunnerState 真源）。
本脚本仅提供命令行入口。

用法:
    python backend/scripts/reconcile.py              # 一次性对账
    python backend/scripts/reconcile.py --daemon 300  # 每 300s 自动运行
"""
import sys
import os
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import log
from services.reconcile_service import reconcile, ReconcileResult  # noqa: E402


def _report(result: ReconcileResult):
    """输出对账报告"""
    ts = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    status = "OK" if result.ok else "FAILED"
    log.info(
        f"[{ts}] Reconcile {status} | "
        f"positions={len(result.exchange_positions)} orders={len(result.exchange_orders)}"
    )
    if result.ok:
        log.info(f"[{ts}] positions={result.exchange_positions}")


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
                for issue in result.issues:
                    log.error(f"  - {issue}")
            await asyncio.sleep(args.daemon)
    else:
        result = await reconcile()
        _report(result)
        if not result.ok:
            for issue in result.issues:
                log.error(f"  - {issue}")
            sys.exit(1)
        else:
            log.info("RECONCILE OK: all positions and orders match")


if __name__ == "__main__":
    asyncio.run(main())
