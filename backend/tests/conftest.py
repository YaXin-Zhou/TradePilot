"""pytest 全局配置 — V5 问题7：测试数据库隔离。

集成测试会真实调用 runner / trading_service 的落库逻辑（_record_closed_trade /
_record_order_success 等），若复用开发库 backend/data/trading.db，会把假成交、
假订单写进仪表盘「最近成交」等真实数据源。此处强制测试使用独立临时库，并在
会话开始时建表，杜绝测试数据污染开发库。
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

# conftest 先于测试模块加载，需自行确保 backend/ 在 sys.path 上
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_TEST_DB_PATH = Path(tempfile.gettempdir()) / "tradepilot_tests" / "test_trading.db"
_TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 关键：必须在任何 config / db.database 导入之前设置环境变量。
# config.py 的 load_dotenv(override=False) 不会覆盖此值。
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """建表 + 清理旧测试数据，保证测试库干净且表结构完整。"""
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()

    from db.database import engine, Base
    import db.models  # noqa: F401  触发所有模型注册到 Base.metadata

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield
