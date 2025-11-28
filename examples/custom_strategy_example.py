"""
自定义策略示例

演示如何继承StrategyBase类实现自定义策略
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from backtesting.strategy_base import StrategyBase


class MACDStrategy(StrategyBase):
    """
    MACD交叉策略示例

    买入条件：MACD金叉
    卖出条件：MACD死叉 或 持有超过20天
    """

    def __init__(self, max_hold_days: int = 20, **params):
        """
        Args:
            max_hold_days: 最大持有天数
        """
        super().__init__(max_hold_days=max_hold_days, **params)
        self.max_hold_days = max_hold_days

    def should_buy(self, ts_code: str, date: str, data: pd.DataFrame,
                   portfolio_value: float, **kwargs) -> bool:
        """
        判断是否买入：MACD金叉

        Args:
            ts_code: 股票代码
            date: 当前日期
            data: 股票历史数据（包含MACD指标）
            portfolio_value: 当前账户总价值
            **kwargs: 其他参数

        Returns:
            是否应该买入
        """
        # 确保数据足够
        if len(data) < 2:
            return False

        # 检查是否有MACD指标
        if 'macd' not in data.columns or 'macd_signal' not in data.columns:
            print(f"警告：{ts_code} 缺少MACD指标")
            return False

        # 获取最近两个交易日的MACD数据
        recent_data = data.tail(2)

        if len(recent_data) < 2:
            return False

        # 前一日
        prev_macd = recent_data.iloc[-2]['macd']
        prev_signal = recent_data.iloc[-2]['macd_signal']

        # 当日
        curr_macd = recent_data.iloc[-1]['macd']
        curr_signal = recent_data.iloc[-1]['macd_signal']

        # MACD金叉：前一日MACD < Signal，当日MACD > Signal
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            print(f"MACD金叉信号：{ts_code} @ {date}")
            return True

        return False

    def should_sell(self, ts_code: str, date: str, data: pd.DataFrame,
                    position: any, **kwargs) -> bool:
        """
        判断是否卖出：MACD死叉 或 超过最大持有天数

        Args:
            ts_code: 股票代码
            date: 当前日期
            data: 股票历史数据
            position: 当前持仓信息
            **kwargs: 其他参数

        Returns:
            是否应该卖出
        """
        # 超过最大持有天数
        if position.hold_days >= self.max_hold_days:
            print(f"超过最大持有天数：{ts_code}, 持有{position.hold_days}天")
            return True

        # 检查MACD死叉
        if len(data) < 2:
            return False

        if 'macd' not in data.columns or 'macd_signal' not in data.columns:
            return False

        recent_data = data.tail(2)
        if len(recent_data) < 2:
            return False

        # 前一日
        prev_macd = recent_data.iloc[-2]['macd']
        prev_signal = recent_data.iloc[-2]['macd_signal']

        # 当日
        curr_macd = recent_data.iloc[-1]['macd']
        curr_signal = recent_data.iloc[-1]['macd_signal']

        # MACD死叉：前一日MACD > Signal，当日MACD < Signal
        if prev_macd >= prev_signal and curr_macd < curr_signal:
            print(f"MACD死叉信号：{ts_code} @ {date}")
            return True

        return False


class RSIStrategy(StrategyBase):
    """
    RSI超买超卖策略示例

    买入条件：RSI < 30（超卖）
    卖出条件：RSI > 70（超买）或 持有超过15天
    """

    def __init__(self, rsi_oversold: float = 30, rsi_overbought: float = 70,
                 max_hold_days: int = 15, **params):
        """
        Args:
            rsi_oversold: RSI超卖阈值
            rsi_overbought: RSI超买阈值
            max_hold_days: 最大持有天数
        """
        super().__init__(
            rsi_oversold=rsi_oversold,
            rsi_overbought=rsi_overbought,
            max_hold_days=max_hold_days,
            **params
        )
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.max_hold_days = max_hold_days

    def should_buy(self, ts_code: str, date: str, data: pd.DataFrame,
                   portfolio_value: float, **kwargs) -> bool:
        """判断是否买入：RSI进入超卖区"""
        if 'rsi' not in data.columns:
            return False

        current_rsi = data.iloc[-1]['rsi']

        if current_rsi < self.rsi_oversold:
            print(f"RSI超卖信号：{ts_code} RSI={current_rsi:.2f}")
            return True

        return False

    def should_sell(self, ts_code: str, date: str, data: pd.DataFrame,
                    position: any, **kwargs) -> bool:
        """判断是否卖出：RSI进入超买区 或 超过最大持有天数"""
        # 超过最大持有天数
        if position.hold_days >= self.max_hold_days:
            return True

        if 'rsi' not in data.columns:
            return False

        current_rsi = data.iloc[-1]['rsi']

        if current_rsi > self.rsi_overbought:
            print(f"RSI超买信号：{ts_code} RSI={current_rsi:.2f}")
            return True

        return False


# 使用示例
if __name__ == '__main__':
    from backtesting import Backtester

    # 创建自定义策略实例
    strategy = MACDStrategy(max_hold_days=20)

    # 或使用RSI策略
    # strategy = RSIStrategy(rsi_oversold=25, rsi_overbought=75, max_hold_days=15)

    # 创建回测器
    backtester = Backtester(
        signals_file='examples/signals.csv',
        strategy=strategy,
        initial_capital=100000
    )

    # 运行回测
    backtester.run()

    # 获取结果
    results = backtester.get_results()

    # 打印交易记录
    print("\n交易记录：")
    print(results['trades'])
