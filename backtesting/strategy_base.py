"""
策略基类模块

定义策略接口，用户可以继承此类实现自定义策略
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import pandas as pd


class StrategyBase(ABC):
    """
    策略基类

    用户可以继承此类实现自定义策略逻辑
    """

    def __init__(self, **params):
        """
        初始化策略

        Args:
            **params: 策略参数
        """
        self.params = params
        self.name = self.__class__.__name__

    @abstractmethod
    def should_buy(self, ts_code: str, date: str, data: pd.DataFrame,
                   portfolio_value: float, **kwargs) -> bool:
        """
        判断是否应该买入

        Args:
            ts_code: 股票代码
            date: 当前日期
            data: 股票历史数据（包含技术指标）
            portfolio_value: 当前账户总价值
            **kwargs: 其他参数

        Returns:
            是否应该买入
        """
        pass

    @abstractmethod
    def should_sell(self, ts_code: str, date: str, data: pd.DataFrame,
                    position: Any, **kwargs) -> bool:
        """
        判断是否应该卖出

        Args:
            ts_code: 股票代码
            date: 当前日期
            data: 股票历史数据（包含技术指标）
            position: 当前持仓信息
            **kwargs: 其他参数

        Returns:
            是否应该卖出
        """
        pass

    def calculate_position_size(self, ts_code: str, date: str, data: pd.DataFrame,
                               available_cash: float, signal_ratio: float,
                               **kwargs) -> float:
        """
        计算买入金额

        Args:
            ts_code: 股票代码
            date: 当前日期
            data: 股票历史数据
            available_cash: 可用资金
            signal_ratio: 信号指定的仓位比例
            **kwargs: 其他参数

        Returns:
            应该买入的金额
        """
        # 默认实现：按信号比例分配资金
        return available_cash * signal_ratio

    def on_trade(self, trade_type: str, ts_code: str, price: float,
                shares: int, date: str, **kwargs):
        """
        交易回调函数（可选实现）

        Args:
            trade_type: 'buy' 或 'sell'
            ts_code: 股票代码
            price: 交易价格
            shares: 交易股数
            date: 交易日期
            **kwargs: 其他参数
        """
        pass

    def get_params(self) -> Dict[str, Any]:
        """获取策略参数"""
        return self.params

    def __repr__(self) -> str:
        return f"{self.name}({self.params})"


class SimpleHoldStrategy(StrategyBase):
    """
    简单持有策略

    在信号日买入，持有指定天数后卖出
    """

    def __init__(self, hold_days: int = 5, **params):
        """
        Args:
            hold_days: 持有天数
        """
        super().__init__(hold_days=hold_days, **params)
        self.hold_days = hold_days

    def should_buy(self, ts_code: str, date: str, data: pd.DataFrame,
                   portfolio_value: float, **kwargs) -> bool:
        """在信号日买入"""
        # 简单持有策略总是在信号触发时买入
        return True

    def should_sell(self, ts_code: str, date: str, data: pd.DataFrame,
                    position: Any, **kwargs) -> bool:
        """持有指定天数后卖出"""
        if position.hold_days >= self.hold_days:
            return True
        return False


class StopLossStrategy(StrategyBase):
    """
    止盈止损策略

    支持固定百分比的止盈和止损
    """

    def __init__(self, stop_loss: float = -0.05, take_profit: float = 0.10,
                 hold_days: int = 30, **params):
        """
        Args:
            stop_loss: 止损比例（负数，如-0.05表示-5%）
            take_profit: 止盈比例（正数，如0.10表示10%）
            hold_days: 最大持有天数
        """
        super().__init__(stop_loss=stop_loss, take_profit=take_profit,
                        hold_days=hold_days, **params)
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.hold_days = hold_days

    def should_buy(self, ts_code: str, date: str, data: pd.DataFrame,
                   portfolio_value: float, **kwargs) -> bool:
        """在信号日买入"""
        return True

    def should_sell(self, ts_code: str, date: str, data: pd.DataFrame,
                    position: Any, **kwargs) -> bool:
        """
        满足以下任一条件卖出：
        1. 收益率达到止盈线
        2. 收益率达到止损线
        3. 持有天数达到上限
        """
        return_rate = position.get_return_rate()

        # 止盈
        if return_rate >= self.take_profit:
            return True

        # 止损
        if return_rate <= self.stop_loss:
            return True

        # 超过最大持有天数
        if position.hold_days >= self.hold_days:
            return True

        return False
