"""
资金账户管理模块

管理回测过程中的资金、持仓和交易记录
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging
from .position import Position, ClosedPosition


class Portfolio:
    """
    投资组合/资金账户管理类

    负责管理资金、持仓、交易记录和账户净值
    """

    def __init__(self,
                 initial_capital: float = 100000.0,
                 commission_rate: float = 0.0003,
                 stamp_tax_rate: float = 0.001,
                 min_commission: float = 5.0,
                 slippage: float = 0.0):
        """
        初始化投资组合

        Args:
            initial_capital: 初始资金
            commission_rate: 佣金费率（默认万3）
            stamp_tax_rate: 印花税率（卖出时收取，默认千1）
            min_commission: 最低佣金（默认5元）
            slippage: 滑点（默认0）
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.commission_rate = commission_rate
        self.stamp_tax_rate = stamp_tax_rate
        self.min_commission = min_commission
        self.slippage = slippage

        # 持仓管理
        self.positions: Dict[str, Position] = {}  # ts_code -> Position
        self.closed_positions: List[ClosedPosition] = []

        # 净值记录
        self.equity_curve: List[dict] = []  # [{date, cash, market_value, total_value}]

        # 统计信息
        self.total_commission = 0.0
        self.total_trades = 0

        self.logger = logging.getLogger(__name__)

    def calculate_commission(self, amount: float, is_buy: bool = True) -> float:
        """
        计算手续费

        Args:
            amount: 交易金额
            is_buy: 是否为买入（卖出时需加印花税）

        Returns:
            手续费总额
        """
        # 佣金
        commission = max(amount * self.commission_rate, self.min_commission)

        # 卖出时加印花税
        if not is_buy:
            stamp_tax = amount * self.stamp_tax_rate
            commission += stamp_tax

        return commission

    def buy(self, ts_code: str, price: float, amount: float, date: str) -> bool:
        """
        买入股票

        Args:
            ts_code: 股票代码
            price: 买入价格
            amount: 买入金额（占总资金的比例对应的金额）
            date: 买入日期

        Returns:
            是否买入成功
        """
        # 应用滑点
        actual_price = price * (1 + self.slippage)

        # 计算手续费
        commission = self.calculate_commission(amount, is_buy=True)
        total_cost = amount + commission

        # 检查资金是否足够
        if total_cost > self.cash:
            self.logger.warning(f"资金不足：需要{total_cost:.2f}，可用{self.cash:.2f}")
            return False

        # 计算股数（向下取整到100的倍数，A股以手为单位）
        shares = int(amount / actual_price / 100) * 100
        if shares == 0:
            self.logger.warning(f"金额太小，无法买入完整手（100股）")
            return False

        # 实际买入金额
        actual_amount = shares * actual_price + commission

        # 创建持仓
        position = Position(
            ts_code=ts_code,
            shares=shares,
            buy_date=date,
            buy_price=actual_price,
            buy_amount=actual_amount,
            current_price=actual_price
        )

        # 更新账户
        self.cash -= actual_amount
        self.positions[ts_code] = position
        self.total_commission += commission
        self.total_trades += 1

        self.logger.info(f"买入成功：{ts_code} {shares}股@{actual_price:.2f} "
                        f"成本{actual_amount:.2f} 手续费{commission:.2f}")
        return True

    def sell(self, ts_code: str, price: float, date: str, notes: str = None) -> bool:
        """
        卖出股票

        Args:
            ts_code: 股票代码
            price: 卖出价格
            date: 卖出日期
            notes: 备注信息

        Returns:
            是否卖出成功
        """
        if ts_code not in self.positions:
            self.logger.warning(f"没有持仓：{ts_code}")
            return False

        position = self.positions[ts_code]

        # 应用滑点
        actual_price = price * (1 - self.slippage)

        # 计算卖出金额
        sell_amount_before_commission = position.shares * actual_price
        commission = self.calculate_commission(sell_amount_before_commission, is_buy=False)
        sell_amount = sell_amount_before_commission - commission

        # 计算总手续费（买入+卖出）
        buy_commission = self.calculate_commission(position.buy_amount -
                                                   self.calculate_commission(position.buy_amount, True),
                                                   is_buy=True)
        total_commission = buy_commission + commission

        # 创建已平仓记录
        closed_position = ClosedPosition.from_position(
            position=position,
            sell_date=date,
            sell_price=actual_price,
            sell_amount=sell_amount,
            commission=total_commission,
            notes=notes
        )

        # 更新账户
        self.cash += sell_amount
        self.closed_positions.append(closed_position)
        del self.positions[ts_code]
        self.total_commission += commission
        self.total_trades += 1

        self.logger.info(f"卖出成功：{ts_code} {position.shares}股@{actual_price:.2f} "
                        f"收入{sell_amount:.2f} 盈亏{closed_position.realized_pnl:.2f}({closed_position.realized_pnl_pct:.2%})")
        return True

    def update_positions(self, prices: Dict[str, float], current_date: str):
        """
        更新所有持仓的当前价格

        Args:
            prices: {ts_code: current_price}
            current_date: 当前日期
        """
        for ts_code, position in self.positions.items():
            if ts_code in prices:
                position.update_price(prices[ts_code], current_date)

    def record_equity(self, date: str):
        """
        记录当前净值

        Args:
            date: 日期
        """
        market_value = sum(pos.current_value for pos in self.positions.values())
        total_value = self.cash + market_value

        self.equity_curve.append({
            'date': date,
            'cash': self.cash,
            'market_value': market_value,
            'total_value': total_value,
            'positions_count': len(self.positions)
        })

    def get_total_value(self) -> float:
        """获取账户总价值"""
        market_value = sum(pos.current_value for pos in self.positions.values())
        return self.cash + market_value

    def get_return_rate(self) -> float:
        """获取总收益率"""
        return (self.get_total_value() - self.initial_capital) / self.initial_capital

    def get_positions_summary(self) -> List[dict]:
        """获取持仓汇总"""
        return [
            {
                '股票代码': pos.ts_code,
                '股数': pos.shares,
                '买入价': round(pos.buy_price, 2),
                '当前价': round(pos.current_price, 2),
                '成本': round(pos.buy_amount, 2),
                '市值': round(pos.current_value, 2),
                '盈亏': round(pos.unrealized_pnl, 2),
                '收益率': f"{pos.unrealized_pnl_pct:.2%}",
                '持仓天数': pos.hold_days
            }
            for pos in self.positions.values()
        ]

    def get_trades_summary(self) -> List[dict]:
        """获取交易记录汇总"""
        return [trade.to_dict() for trade in self.closed_positions]

    def __repr__(self) -> str:
        return (f"Portfolio(cash={self.cash:.2f}, "
                f"positions={len(self.positions)}, "
                f"total_value={self.get_total_value():.2f}, "
                f"return={self.get_return_rate():.2%})")
