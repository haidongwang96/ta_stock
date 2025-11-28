"""
回测指标计算模块

计算各种回测性能指标
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime


class BacktestMetrics:
    """
    回测指标计算类

    计算收益率、风险指标、交易统计等
    """

    def __init__(self, equity_curve: pd.DataFrame, closed_trades: pd.DataFrame,
                 initial_capital: float, risk_free_rate: float = 0.03):
        """
        初始化指标计算器

        Args:
            equity_curve: 净值曲线（包含date, total_value列）
            closed_trades: 已平仓交易记录
            initial_capital: 初始资金
            risk_free_rate: 无风险利率（年化，默认3%）
        """
        self.equity_curve = equity_curve
        self.closed_trades = closed_trades
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate

        # 计算日收益率
        if not equity_curve.empty:
            self.equity_curve['returns'] = self.equity_curve['total_value'].pct_change()
            self.equity_curve['cum_returns'] = (1 + self.equity_curve['returns']).cumprod() - 1

    def calculate_all_metrics(self) -> Dict[str, any]:
        """
        计算所有指标

        Returns:
            包含所有指标的字典
        """
        metrics = {}

        # 收益指标
        metrics.update(self._calculate_return_metrics())

        # 风险指标
        metrics.update(self._calculate_risk_metrics())

        # 交易统计
        metrics.update(self._calculate_trade_stats())

        # 时间统计
        metrics.update(self._calculate_time_stats())

        return metrics

    def _calculate_return_metrics(self) -> Dict[str, float]:
        """计算收益指标"""
        if self.equity_curve.empty:
            return {}

        final_value = self.equity_curve['total_value'].iloc[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital

        # 计算年化收益率
        start_date = pd.to_datetime(self.equity_curve['date'].iloc[0], format='%Y%m%d')
        end_date = pd.to_datetime(self.equity_curve['date'].iloc[-1], format='%Y%m%d')
        days = (end_date - start_date).days
        years = days / 365.0
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'final_value': final_value,
            'total_pnl': final_value - self.initial_capital
        }

    def _calculate_risk_metrics(self) -> Dict[str, float]:
        """计算风险指标"""
        if self.equity_curve.empty or len(self.equity_curve) < 2:
            return {}

        returns = self.equity_curve['returns'].dropna()

        # 波动率（年化）
        volatility = returns.std() * np.sqrt(252)

        # 最大回撤
        cum_max = self.equity_curve['total_value'].cummax()
        drawdown = (self.equity_curve['total_value'] - cum_max) / cum_max
        max_drawdown = drawdown.min()

        # 最大回撤持续期（天数）
        dd_duration = self._calculate_max_drawdown_duration(drawdown)

        # 夏普比率（年化）
        excess_returns = returns.mean() * 252 - self.risk_free_rate
        sharpe_ratio = excess_returns / volatility if volatility > 0 else 0

        # 索提诺比率（只考虑下行风险）
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252)
        sortino_ratio = excess_returns / downside_std if downside_std > 0 else 0

        # 卡玛比率（收益/最大回撤）
        calmar_ratio = abs(self._calculate_return_metrics()['annual_return'] / max_drawdown) if max_drawdown < 0 else 0

        return {
            'volatility': volatility,
            'max_drawdown': max_drawdown,
            'max_drawdown_duration': dd_duration,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio
        }

    def _calculate_max_drawdown_duration(self, drawdown: pd.Series) -> int:
        """计算最大回撤持续期"""
        is_drawdown = drawdown < 0
        drawdown_groups = (is_drawdown != is_drawdown.shift()).cumsum()

        max_duration = 0
        for group_id in drawdown_groups[is_drawdown].unique():
            duration = (drawdown_groups == group_id).sum()
            max_duration = max(max_duration, duration)

        return max_duration

    def _calculate_trade_stats(self) -> Dict[str, any]:
        """计算交易统计"""
        if self.closed_trades.empty:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'avg_hold_days': 0
            }

        # 解析收益率（从字符串格式如"5.20%"转换为浮点数）
        def parse_return_rate(rate_str):
            if isinstance(rate_str, str):
                return float(rate_str.strip('%')) / 100
            return rate_str

        # 如果盈亏列存在，直接使用
        if '盈亏' in self.closed_trades.columns:
            pnl = self.closed_trades['盈亏']
        elif 'realized_pnl' in self.closed_trades.columns:
            pnl = self.closed_trades['realized_pnl']
        else:
            pnl = pd.Series([0])

        winning_trades = pnl[pnl > 0]
        losing_trades = pnl[pnl < 0]

        total_trades = len(self.closed_trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)

        win_rate = win_count / total_trades if total_trades > 0 else 0
        avg_win = winning_trades.mean() if not winning_trades.empty else 0
        avg_loss = abs(losing_trades.mean()) if not losing_trades.empty else 0

        total_profit = winning_trades.sum()
        total_loss = abs(losing_trades.sum())
        profit_factor = total_profit / total_loss if total_loss > 0 else 0

        # 平均持仓天数
        if '持仓天数' in self.closed_trades.columns:
            avg_hold_days = self.closed_trades['持仓天数'].mean()
        elif 'hold_days' in self.closed_trades.columns:
            avg_hold_days = self.closed_trades['hold_days'].mean()
        else:
            avg_hold_days = 0

        return {
            'total_trades': total_trades,
            'win_count': win_count,
            'loss_count': loss_count,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_hold_days': avg_hold_days,
            'largest_win': pnl.max() if not pnl.empty else 0,
            'largest_loss': pnl.min() if not pnl.empty else 0
        }

    def _calculate_time_stats(self) -> Dict[str, any]:
        """计算时间统计"""
        if self.equity_curve.empty:
            return {}

        start_date = self.equity_curve['date'].iloc[0]
        end_date = self.equity_curve['date'].iloc[-1]

        start_dt = pd.to_datetime(start_date, format='%Y%m%d')
        end_dt = pd.to_datetime(end_date, format='%Y%m%d')

        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_days': (end_dt - start_dt).days,
            'trading_days': len(self.equity_curve)
        }

    def get_monthly_returns(self) -> pd.DataFrame:
        """
        计算月度收益率

        Returns:
            月度收益率DataFrame
        """
        if self.equity_curve.empty:
            return pd.DataFrame()

        df = self.equity_curve.copy()
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df['year_month'] = df['date'].dt.to_period('M')

        # 每月最后一天的收益率
        monthly = df.groupby('year_month')['total_value'].last()
        monthly_returns = monthly.pct_change()

        return pd.DataFrame({
            'month': monthly_returns.index.astype(str),
            'return': monthly_returns.values
        })

    def print_metrics(self):
        """打印所有指标"""
        metrics = self.calculate_all_metrics()

        print("\n" + "=" * 60)
        print("详细回测指标")
        print("=" * 60)

        print("\n【收益指标】")
        print(f"总收益率：{metrics.get('total_return', 0):.2%}")
        print(f"年化收益率：{metrics.get('annual_return', 0):.2%}")
        print(f"总盈亏：{metrics.get('total_pnl', 0):,.2f}")
        print(f"最终资金：{metrics.get('final_value', 0):,.2f}")

        print("\n【风险指标】")
        print(f"波动率（年化）：{metrics.get('volatility', 0):.2%}")
        print(f"最大回撤：{metrics.get('max_drawdown', 0):.2%}")
        print(f"最大回撤持续期：{metrics.get('max_drawdown_duration', 0)} 天")
        print(f"夏普比率：{metrics.get('sharpe_ratio', 0):.2f}")
        print(f"索提诺比率：{metrics.get('sortino_ratio', 0):.2f}")
        print(f"卡玛比率：{metrics.get('calmar_ratio', 0):.2f}")

        print("\n【交易统计】")
        print(f"总交易次数：{metrics.get('total_trades', 0)}")
        print(f"盈利次数：{metrics.get('win_count', 0)}")
        print(f"亏损次数：{metrics.get('loss_count', 0)}")
        print(f"胜率：{metrics.get('win_rate', 0):.2%}")
        print(f"平均盈利：{metrics.get('avg_win', 0):,.2f}")
        print(f"平均亏损：{metrics.get('avg_loss', 0):,.2f}")
        print(f"盈亏比：{metrics.get('profit_factor', 0):.2f}")
        print(f"平均持仓天数：{metrics.get('avg_hold_days', 0):.1f}")
        print(f"最大单笔盈利：{metrics.get('largest_win', 0):,.2f}")
        print(f"最大单笔亏损：{metrics.get('largest_loss', 0):,.2f}")

        print("\n【时间统计】")
        print(f"开始日期：{metrics.get('start_date', 'N/A')}")
        print(f"结束日期：{metrics.get('end_date', 'N/A')}")
        print(f"总天数：{metrics.get('total_days', 0)}")
        print(f"交易日数：{metrics.get('trading_days', 0)}")

        print("=" * 60 + "\n")

    def to_dict(self) -> Dict[str, any]:
        """转换为字典格式，便于保存"""
        return self.calculate_all_metrics()
