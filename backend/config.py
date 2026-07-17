"""
AI 量化交易系统 - 全局配置
"""
import os
from pathlib import Path


class Settings:
    # 项目路径
    ROOT = Path(__file__).parent

    # 数据库
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{ROOT}/data/trading.db")
    ECHO_SQL: bool = False

    # 交易所 (默认 OKX)
    EXCHANGE_NAME: str = os.getenv("EXCHANGE_NAME", "okx")
    EXCHANGE_API_KEY: str = os.getenv("EXCHANGE_API_KEY", "")
    EXCHANGE_SECRET: str = os.getenv("EXCHANGE_SECRET", "")
    EXCHANGE_PASSPHRASE: str = os.getenv("EXCHANGE_PASSPHRASE", "")
    EXCHANGE_TESTNET: bool = os.getenv("EXCHANGE_TESTNET", "true").lower() == "true"

    # 默认交易对
    DEFAULT_SYMBOL: str = os.getenv("DEFAULT_SYMBOL", "BTC/USDT")

    # 服务器
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # CORS
    CORS_ORIGINS: list[str] = ['*']

    # 策略默认参数
    DEFAULT_GRID_LOWER: float = 83000.0
    DEFAULT_GRID_UPPER: float = 93000.0
    DEFAULT_GRID_COUNT: int = 20
    DEFAULT_ORDER_AMOUNT: float = 100.0
    DEFAULT_MAX_INVESTMENT: float = 2000.0

    # ML 参数
    ML_MODEL_PATH: str = str(ROOT / "ml" / "models")
    ML_SEQUENCE_LENGTH: int = 60
    ML_TRAIN_INTERVAL_HOURS: int = 24

    # 风险控制
    MAX_POSITION_SIZE_USDT: float = 5000.0
    MAX_DAILY_LOSS_PCT: float = 5.0
    STOP_LOSS_PCT: float = 10.0
    MAX_OPEN_ORDERS: int = 50


settings = Settings()

