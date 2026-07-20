"""v1.3 U2: GridEngine — 纯函数网格穿越检测引擎

从 grid_trading/grid_bot.py 提取核心算法，无副作用、无 IO。
与 trading_service 组合使用，作为 GRID 策略的核心逻辑。

设计：
  - 所有方法为纯函数或简单状态计算（不涉及交易所 IO）
  - GridConfig 定义网格参数
  - GridState 追踪运行时状态（由策略层管理持久化）
"""

from dataclasses import dataclass, field
import math


@dataclass
class GridConfig:
    """网格策略配置"""
    symbol: str
    lower_price: float
    upper_price: float
    grid_count: int
    investment_total: float
    stop_loss_pct: float = 10.0
    order_amount: float = 100.0

    @property
    def grid_spacing(self) -> float:
        """网格间距"""
        return (self.upper_price - self.lower_price) / self.grid_count

    @property
    def order_amount_per_grid(self) -> float:
        """每格下单金额"""
        return self.investment_total / self.grid_count


@dataclass
class GridState:
    """网格运行时状态"""
    lines: list[float] = field(default_factory=list)
    buy_orders: dict[int, str] = field(default_factory=dict)   # level_idx → exchange_order_id
    sell_orders: dict[int, str] = field(default_factory=dict)  # level_idx → exchange_order_id
    pending_sells: dict[int, float] = field(default_factory=dict)  # level_idx → qty
    avg_entry: float = 0.0
    total_qty: float = 0.0


class GridEngine:
    """纯函数网格引擎 — 无副作用"""

    @staticmethod
    def compute_lines(config: GridConfig) -> list[float]:
        """计算网格线价格列表（从低到高）"""
        lines = []
        for i in range(config.grid_count + 1):
            price = config.lower_price + i * config.grid_spacing
            lines.append(round(price, 2))
        return lines

    @staticmethod
    def detect_cross(price: float, lines: list[float]) -> list[int]:
        """检测价格穿越了哪些网格线（返回穿过的 level index 列表）

        穿越条件：价格从 line[i] 上方穿过到下方，或反之。
        简化实现：返回当前价格所在 level 及相邻 level。
        """
        crossed = []
        for i, line in enumerate(lines[:-1]):
            if lines[i] <= price <= lines[i + 1]:
                crossed.append(i)
                if i > 0:
                    crossed.append(i - 1)
                if i < len(lines) - 2:
                    crossed.append(i + 1)
                break
        return list(set(crossed))

    @staticmethod
    def should_place_buy(level_idx: int, state: GridState) -> bool:
        """是否应在指定 level 挂买单"""
        return level_idx not in state.buy_orders and level_idx not in state.pending_sells

    @staticmethod
    def get_sell_price(buy_level_idx: int, config: GridConfig) -> float:
        """买入 level 对应的卖出价格（上一格）"""
        sell_idx = min(buy_level_idx + 1, config.grid_count)
        return config.lower_price + sell_idx * config.grid_spacing

    @staticmethod
    def should_stop_loss(avg_entry: float, current_price: float, config: GridConfig) -> bool:
        """判断是否触发止损"""
        if avg_entry <= 0:
            return False
        loss_pct = (avg_entry - current_price) / avg_entry * 100
        return loss_pct >= config.stop_loss_pct

    @staticmethod
    def calculate_grid_per_order(config: GridConfig) -> float:
        """计算每笔下单数量（BTC 单位）"""
        if config.lower_price <= 0:
            return 0.0
        return config.order_amount / config.lower_price

    @staticmethod
    def is_price_out_of_range(price: float, config: GridConfig) -> bool:
        """价格是否超出网格范围"""
        return price < config.lower_price or price > config.upper_price
