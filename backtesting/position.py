"""
持仓管理模块

管理单个股票的持仓信息
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Position:
    """
    持仓数据类

    Attributes:
        ts_code: 股票代码
        shares: 持仓股数
        buy_date: 买入日期
        buy_price: 买入价格
        buy_amount: 买入金额（含手续费）
        current_price: 当前价格
        current_value: 当前市值
        unrealized_pnl: 未实现盈亏
        unrealized_pnl_pct: 未实现盈亏比例
        hold_days: 持仓天数
    """
    ts_code: str
    shares: int
    buy_date: str
    buy_price: float
    buy_amount: float
    current_price: float = 0.0
    current_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    hold_days: int = 0

    def update_price(self, new_price: float, current_date: str):
        """
        更新当前价格和持仓信息

        Args:
            new_price: 最新价格
            current_date: 当前日期（YYYYMMDD格式）
        """
        self.current_price = new_price
        self.current_value = self.shares * new_price
        self.unrealized_pnl = self.current_value - self.buy_amount
        self.unrealized_pnl_pct = (self.unrealized_pnl / self.buy_amount) if self.buy_amount > 0 else 0.0

        # 计算持仓天数
        buy_dt = datetime.strptime(self.buy_date, '%Y%m%d')
        current_dt = datetime.strptime(current_date, '%Y%m%d')
        self.hold_days = (current_dt - buy_dt).days

    def get_return_rate(self) -> float:
        """获取收益率"""
        return self.unrealized_pnl_pct

    def __repr__(self) -> str:
        return (f"Position({self.ts_code}, "
                f"shares={self.shares}, "
                f"buy_price={self.buy_price:.2f}, "
                f"current_price={self.current_price:.2f}, "
                f"pnl={self.unrealized_pnl_pct:.2%})")


@dataclass
class ClosedPosition:
    """
    已平仓记录

    用于记录完整的交易记录
    """
    ts_code: str
    shares: int
    buy_date: str
    buy_price: float
    buy_amount: float
    sell_date: str
    sell_price: float
    sell_amount: float
    realized_pnl: float
    realized_pnl_pct: float
    hold_days: int
    commission: float  # 总手续费
    notes: Optional[str] = None

    @classmethod
    def from_position(cls, position: Position, sell_date: str, sell_price: float,
                     sell_amount: float, commission: float, notes: Optional[str] = None):
        """
        从持仓对象创建已平仓记录

        Args:
            position: 持仓对象
            sell_date: 卖出日期
            sell_price: 卖出价格
            sell_amount: 卖出金额（扣除手续费后）
            commission: 总手续费（买入+卖出）
            notes: 备注
        """
        realized_pnl = sell_amount - position.buy_amount
        realized_pnl_pct = realized_pnl / position.buy_amount if position.buy_amount > 0 else 0.0

        buy_dt = datetime.strptime(position.buy_date, '%Y%m%d')
        sell_dt = datetime.strptime(sell_date, '%Y%m%d')
        hold_days = (sell_dt - buy_dt).days

        return cls(
            ts_code=position.ts_code,
            shares=position.shares,
            buy_date=position.buy_date,
            buy_price=position.buy_price,
            buy_amount=position.buy_amount,
            sell_date=sell_date,
            sell_price=sell_price,
            sell_amount=sell_amount,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            hold_days=hold_days,
            commission=commission,
            notes=notes
        )

    def to_dict(self) -> dict:
        """转换为字典格式，便于保存"""
        return {
            '股票代码': self.ts_code,
            '股数': self.shares,
            '买入日期': self.buy_date,
            '买入价格': round(self.buy_price, 2),
            '买入金额': round(self.buy_amount, 2),
            '卖出日期': self.sell_date,
            '卖出价格': round(self.sell_price, 2),
            '卖出金额': round(self.sell_amount, 2),
            '盈亏': round(self.realized_pnl, 2),
            '收益率': f"{self.realized_pnl_pct:.2%}",
            '持仓天数': self.hold_days,
            '手续费': round(self.commission, 2),
            '备注': self.notes or ''
        }

    def __repr__(self) -> str:
        return (f"ClosedPosition({self.ts_code}, "
                f"buy={self.buy_date}@{self.buy_price:.2f}, "
                f"sell={self.sell_date}@{self.sell_price:.2f}, "
                f"pnl={self.realized_pnl_pct:.2%}, "
                f"days={self.hold_days})")
