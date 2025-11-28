"""
股票回测框架

这个模块提供了一个灵活、可扩展的股票回测框架，支持：
- CSV信号文件输入
- 自定义策略接口
- 资金管理和持仓跟踪
- 详细的收益指标计算
- 可视化图表生成
"""

from .backtester import Backtester
from .trade_signal import TradeSignal
from .position import Position
from .portfolio import Portfolio
from .strategy_base import StrategyBase
from .metrics import BacktestMetrics
from .visualizer import BacktestVisualizer

__all__ = [
    'Backtester',
    'TradeSignal',
    'Position',
    'Portfolio',
    'StrategyBase',
    'BacktestMetrics',
    'BacktestVisualizer'
]

__version__ = '1.0.0'
