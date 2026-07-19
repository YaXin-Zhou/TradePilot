"""数据库模型定义"""
import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, BigInteger, Boolean, DateTime, Text, Enum, JSON, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from db.database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _uuid():
    return str(uuid.uuid4())[:8]


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    FAILED = "failed"


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    LIMIT = "limit"
    MARKET = "market"


class StrategyType(str, enum.Enum):
    """统一策略类型枚举 — 全系统唯一来源（Phase 7.1 统一）"""
    # 旧值（向后兼容已存数据）
    GRID = "grid"
    ML_SIGNAL = "ml_signal"
    SMA_CROSS = "sma_cross"
    CUSTOM = "custom"
    # 新增（Phase 4 风控引擎所需）
    MA_CROSS = "ma_cross"
    RSI = "rsi"
    BOLLINGER = "bollinger"
    AI_GENERATED = "ai_generated"


class StrategyStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String(64), unique=True, nullable=False)
    email = Column(String(128), unique=True, nullable=True)
    hashed_password = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    strategies = relationship("Strategy", back_populates="user")
    orders = relationship("Order", back_populates="user")


class Strategy(Base):
    __tablename__ = "strategies"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), default="default")
    name = Column(String(128), nullable=False)
    type = Column(Enum(StrategyType), nullable=False)
    status = Column(Enum(StrategyStatus), default=StrategyStatus.DRAFT)
    config = Column(JSON, default=dict)
    symbol = Column(String(32), default="BTC/USDT")
    total_pnl = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="strategies")
    orders = relationship("Order", back_populates="strategy")
    positions = relationship("Position", back_populates="strategy")


class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), default="default")
    account_id = Column(String(64), default="default", index=True)  # M1: 多账户支持
    strategy_id = Column(String, ForeignKey("strategies.id"), nullable=True)
    symbol = Column(String(32), nullable=False)
    side = Column(Enum(OrderSide), nullable=False)
    type = Column(Enum(OrderType), default=OrderType.LIMIT)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    filled = Column(Float, default=0.0)
    cost = Column(Float, default=0.0)
    exchange_order_id = Column(String(128), nullable=True)
    idempotency_key = Column(String(128), nullable=True, index=True)  # M3: 幂等键防重复下单
    raw = Column(JSON, nullable=True)  # M3: 交易所原始返回
    created_at = Column(DateTime, default=_utcnow)
    filled_at = Column(DateTime, nullable=True)
    user = relationship("User", back_populates="orders")
    strategy = relationship("Strategy", back_populates="orders")


class Trade(Base):
    __tablename__ = "trades"
    id = Column(String, primary_key=True, default=_uuid)
    strategy_id = Column(String, ForeignKey("strategies.id"), nullable=True)
    symbol = Column(String(32), nullable=False)
    buy_price = Column(Float, nullable=False)
    sell_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    profit = Column(Float, default=0.0)
    profit_pct = Column(Float, default=0.0)
    buy_order_id = Column(String, nullable=True)
    sell_order_id = Column(String, nullable=True)
    opened_at = Column(DateTime, default=_utcnow)
    closed_at = Column(DateTime, nullable=True)


class Position(Base):
    __tablename__ = "positions"
    id = Column(String, primary_key=True, default=_uuid)
    strategy_id = Column(String, ForeignKey("strategies.id"), nullable=True)
    symbol = Column(String(32), nullable=False)
    quantity = Column(Float, default=0.0)
    avg_entry_price = Column(Float, default=0.0)
    current_value = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    strategy = relationship("Strategy", back_populates="positions")


class MarketData(Base):
    __tablename__ = "market_data"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False)
    timeframe = Column(String(8), default="1h")
    timestamp = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_ohlcv"),
    )


class MLPrediction(Base):
    __tablename__ = "ml_predictions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False)
    timeframe = Column(String(8), default="1h")
    predicted_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    predicted_change_pct = Column(Float, nullable=False)
    confidence = Column(Float, default=0.0)
    signal = Column(String(16), default="neutral")
    model_name = Column(String(64), default="xgboost")
    features_used = Column(JSON, default=list)
    created_at = Column(DateTime, default=_utcnow)


class BacktestResult(Base):
    __tablename__ = "backtest_results"
    id = Column(String, primary_key=True, default=_uuid)
    strategy_id = Column(String, ForeignKey("strategies.id"), nullable=True)
    symbol = Column(String(32), nullable=False)
    timeframe = Column(String(8), default="1h")
    total_pnl = Column(Float, default=0.0)
    total_pnl_pct = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    config_snapshot = Column(JSON, default=dict)
    trades = Column(JSON, default=list)
    created_at = Column(DateTime, default=_utcnow)




class AppConfig(Base):
    __tablename__ = "app_config"
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(Text, default="")


# ---------------------------------------------------------------------------
# M1 · 生产级扩表：审计日志 + 多租户凭据 + 策略运行状态
# ---------------------------------------------------------------------------

class AuditLog(Base):
    """审计日志 — 记录所有关键操作（下单/撤单/配置变更/紧急停止等）"""
    __tablename__ = "audit_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_time = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor = Column(String(64))                     # user_id / "system" / "scheduler"
    action = Column(String(128))                   # "place_order" / "kill_switch" / "config_change"
    entity_type = Column(String(64))               # "order" / "strategy" / "credential"
    entity_id = Column(String(64))
    detail = Column(JSON)                          # 完整 payload（幂等 key、价格、数量等）
    result = Column(String(16))                    # "ok" / "error"
    error_msg = Column(Text, nullable=True)


class ExchangeCredential(Base):
    """多租户交易所凭据 — AES-256-GCM 加密存储"""
    __tablename__ = "exchange_credentials"
    id = Column(String, primary_key=True, default=_uuid)
    tenant_id = Column(String(64), default="default", index=True)
    account_label = Column(String(128), nullable=False)
    exchange_id = Column(String(32), default="okx")  # "binance" / "okx" / ...
    api_key_enc = Column(Text)                       # AES-256-GCM 加密
    api_secret_enc = Column(Text)
    passphrase_enc = Column(Text, nullable=True)
    is_testnet = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_label", name="uq_tenant_account"),
    )


class RunnerState(Base):
    """策略运行状态 — 替代 runner_state.json，支持多实例乐观锁"""
    __tablename__ = "runner_states"
    strategy_id = Column(String, ForeignKey("strategies.id"), primary_key=True)
    position_side = Column(String(8), default="none")   # "long" / "short" / "none"
    entry_price = Column(Float, nullable=True)
    entry_size = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    locked_by = Column(String(64), nullable=True)        # instance_id，乐观锁
    lock_expires = Column(DateTime, nullable=True)
    extra = Column(JSON, default=dict)                   # 扩展字段（网格状态等）


# ---------------------------------------------------------------------------
# P0-1 · kill_switch + risk_engine 迁入 DB（消除 JSON 文件竞态）
# ---------------------------------------------------------------------------

class KillSwitchStateRecord(Base):
    """Kill switch 状态 — 替代 kill_switch.json，支持多 worker 一致性

    单行表（id 恒为 1），存储全局紧急停止状态。
    多 worker 共享同一行，一个 worker 触发后其他 worker 可通过 refresh 读取。
    """
    __tablename__ = "kill_switch_state"
    id = Column(Integer, primary_key=True, default=1)  # 单行表
    status = Column(String(16), default="ARMED")       # ARMED / TRIGGERED
    triggered_at = Column(Float, nullable=True)        # Unix timestamp
    triggered_by = Column(String(64), nullable=True)
    reason = Column(Text, nullable=True)
    actions_taken = Column(JSON, default=list)
    orders_cancelled = Column(Integer, default=0)
    positions_closed = Column(Integer, default=0)
    strategies_stopped = Column(Integer, default=0)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class RiskPolicyRecord(Base):
    """风控策略 — 替代 risk_policies.json，支持多 worker 一致性

    每个 MarketRegime 一行，存储该 regime 的风控参数。
    """
    __tablename__ = "risk_policies"
    regime = Column(String(32), primary_key=True)       # MarketRegime.value
    max_position_pct = Column(Float, default=0.3)
    max_single_strategy_pct = Column(Float, default=0.15)
    max_daily_loss_pct = Column(Float, default=5.0)
    stop_loss_pct = Column(Float, default=8.0)
    trailing_stop_pct = Column(Float, default=3.0)
    min_sharpe_entry = Column(Float, default=0.8)
    max_correlation = Column(Float, default=0.7)
    time_stop_hours = Column(Integer, default=72)
    atr_stop_multiplier = Column(Float, default=2.0)
    allowed_strategies = Column(JSON, default=list)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
