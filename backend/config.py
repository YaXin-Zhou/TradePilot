"""
AI 量化交易系统 - 全局配置
"""
from dotenv import load_dotenv
import os
from pathlib import Path

# Load .env from backend directory
load_dotenv(Path(__file__).parent / ".env")


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

    # 代理
    HTTPS_PROXY: str = os.getenv("HTTPS_PROXY", "")
    HTTP_PROXY: str = os.getenv("HTTP_PROXY", "")

    # 加密密钥 (Fernet AES)
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # AI
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

    # JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "ai_quant_jwt_secret_key_dev")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

    # CORS — 默认允许本地开发常用端口（3000/3001/3002）
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001,"
        "http://localhost:3002,http://127.0.0.1:3002",
    ).split(",")

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

    # 风险控制 — 保守档（用户确认）：单笔≤200，总持仓≤2000
    MAX_ORDER_AMOUNT_USDT: float = float(os.getenv("MAX_ORDER_AMOUNT_USDT", "200.0"))   # 单笔下单硬上限
    MAX_TOTAL_POSITION_USDT: float = float(os.getenv("MAX_TOTAL_POSITION_USDT", "2000.0"))  # 总持仓硬上限
    MAX_POSITION_SIZE_USDT: float = 5000.0
    MAX_DAILY_LOSS_PCT: float = 5.0
    STOP_LOSS_PCT: float = 10.0
    MAX_OPEN_ORDERS: int = 50

    # 实盘交易对白名单（逗号分隔，空=不限制但不推荐）
    LIVE_SYMBOL_WHITELIST: list[str] = [
        s.strip() for s in os.getenv(
            "LIVE_SYMBOL_WHITELIST", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT"
        ).split(",") if s.strip()
    ]

    # AI 功能在实盘模式是否禁用（用户确认：实盘先关，模拟盘用）
    DISABLE_AI_IN_LIVE: bool = os.getenv("DISABLE_AI_IN_LIVE", "true").lower() == "true"

    # ------------------------------------------------------------------
    # 安全校验（Phase 7.7）
    # ------------------------------------------------------------------

    JWT_DEFAULT_KEY: str = "ai_quant_jwt_secret_key_dev"

    def validate_security(self) -> list[str]:
        """启动时安全检查，返回告警列表（空=全部通过）。

        生产模式（DEBUG=False）下使用默认 JWT 密钥 → 拒绝启动。
        """
        warnings: list[str] = []

        if self.JWT_SECRET_KEY == self.JWT_DEFAULT_KEY:
            if not self.DEBUG:
                raise RuntimeError(
                    "FATAL: JWT_SECRET_KEY 仍为默认值且非 DEBUG 模式。"
                    "生产环境必须设置 JWT_SECRET_KEY 环境变量（>= 32 字符随机串）。"
                )
            else:
                warnings.append(
                    "JWT_SECRET_KEY 使用默认值（仅开发模式允许，生产前必须设置环境变量）"
                )

        if self.ENCRYPTION_KEY == "" and not self.DEBUG:
            warnings.append("ENCRYPTION_KEY 未设置（生产建议显式配置）")

        return warnings


settings = Settings()


