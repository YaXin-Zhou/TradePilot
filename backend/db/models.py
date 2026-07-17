"""数据库模型定义"""
import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, Enum, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from db.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


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
    GRID = "grid"
    ML_SIGNAL = "ml_signal"
    SMA_CROSS = "sma_cross"
    CUSTOM = "custom"


class StrategyStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String(64), default="Trader")
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

