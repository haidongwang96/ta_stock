"""
回测引擎核心模块

实现股票回测的主要逻辑
"""

import pandas as pd
import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.query_helper import StockDataQuery
from .trade_signal import TradeSignal
from .portfolio import Portfolio
from .strategy_base import StrategyBase, SimpleHoldStrategy


class Backtester:
    """
    回测引擎

    负责读取信号、获取历史数据、执行交易、记录结果
    """

    def __init__(self,
                 signals_file: str,
                 strategy: Optional[StrategyBase] = None,
                 initial_capital: float = 100000.0,
                 commission_rate: float = 0.0003,
                 stamp_tax_rate: float = 0.001,
                 min_commission: float = 5.0,
                 slippage: float = 0.0,
                 db_path: str = None):
        """
        初始化回测引擎

        Args:
            signals_file: 信号文件路径（CSV格式）
            strategy: 交易策略（默认使用SimpleHoldStrategy）
            initial_capital: 初始资金
            commission_rate: 佣金费率
            stamp_tax_rate: 印花税率
            min_commission: 最低佣金
            slippage: 滑点
            db_path: 数据库路径（默认使用项目下的stock_data.db）
        """
        self.signals_file = signals_file
        self.strategy = strategy or SimpleHoldStrategy(hold_days=5)
        self.initial_capital = initial_capital

        # 初始化投资组合
        self.portfolio = Portfolio(
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            stamp_tax_rate=stamp_tax_rate,
            min_commission=min_commission,
            slippage=slippage
        )

        # 初始化数据查询
        if db_path is None:
            # 默认使用项目根目录下的数据库
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, 'stock_data.db')

        self.data_query = StockDataQuery(db_path)

        # 交易信号
        self.signals: List[TradeSignal] = []

        # 回测状态
        self.start_date: Optional[str] = None
        self.end_date: Optional[str] = None
        self.trading_days: List[str] = []

        self.logger = logging.getLogger(__name__)

    def load_signals(self) -> bool:
        """
        从CSV文件加载交易信号

        CSV格式：ts_code,trade_date,position_ratio
        """
        try:
            df = pd.read_csv(self.signals_file)

            # 验证必需的列
            required_cols = ['ts_code', 'trade_date', 'position_ratio']
            if not all(col in df.columns for col in required_cols):
                self.logger.error(f"CSV文件缺少必需的列：{required_cols}")
                return False

            # 转换为TradeSignal对象
            for _, row in df.iterrows():
                signal = TradeSignal(
                    ts_code=row['ts_code'],
                    trade_date=str(row['trade_date']).zfill(8),
                    position_ratio=float(row['position_ratio'])
                )
                self.signals.append(signal)

            self.logger.info(f"成功加载 {len(self.signals)} 条交易信号")
            return True

        except Exception as e:
            self.logger.error(f"加载信号文件失败：{e}")
            return False

    def prepare_backtest(self) -> bool:
        """
        准备回测环境

        1. 确定回测的时间范围
        2. 预加载所有需要的股票数据
        """
        if not self.signals:
            self.logger.error("没有交易信号，请先加载信号文件")
            return False

        # 确定时间范围
        signal_dates = [s.trade_date for s in self.signals]
        self.start_date = min(signal_dates)

        # 结束日期设置为最后一个信号日期后的60天（或当前日期）
        last_signal_date = datetime.strptime(max(signal_dates), '%Y%m%d')
        end_date_candidate = last_signal_date + timedelta(days=60)
        self.end_date = min(end_date_candidate, datetime.now()).strftime('%Y%m%d')

        self.logger.info(f"回测时间范围：{self.start_date} - {self.end_date}")

        # 获取所有涉及的股票列表
        stock_codes = list(set(s.ts_code for s in self.signals))
        self.logger.info(f"涉及股票数量：{len(stock_codes)}")

        return True

    def run(self) -> bool:
        """
        运行回测

        Returns:
            是否成功完成回测
        """
        if not self.load_signals():
            return False

        if not self.prepare_backtest():
            return False

        # 按日期分组信号
        signals_by_date: Dict[str, List[TradeSignal]] = {}
        for signal in self.signals:
            if signal.trade_date not in signals_by_date:
                signals_by_date[signal.trade_date] = []
            signals_by_date[signal.trade_date].append(signal)

        # 获取所有交易日列表
        all_dates = sorted(signals_by_date.keys())
        start_dt = datetime.strptime(self.start_date, '%Y%m%d')
        end_dt = datetime.strptime(self.end_date, '%Y%m%d')

        # 生成交易日列表（简化版，实际应该从数据库获取）
        current_date = start_dt
        while current_date <= end_dt:
            date_str = current_date.strftime('%Y%m%d')
            self.trading_days.append(date_str)
            current_date += timedelta(days=1)

        self.logger.info(f"开始回测，共 {len(self.trading_days)} 个日期")

        # 按日期模拟交易
        for i, current_date in enumerate(self.trading_days):
            # 处理买入信号
            if current_date in signals_by_date:
                for signal in signals_by_date[current_date]:
                    self._process_buy_signal(signal, current_date)

            # 更新持仓和检查卖出
            self._update_and_check_sell(current_date)

            # 记录净值
            self.portfolio.record_equity(current_date)

            # 进度显示
            if (i + 1) % 50 == 0 or i == len(self.trading_days) - 1:
                self.logger.info(f"进度：{i + 1}/{len(self.trading_days)}，"
                               f"账户价值：{self.portfolio.get_total_value():.2f}，"
                               f"持仓数：{len(self.portfolio.positions)}")

        # 回测结束，强制平仓所有持仓
        self._close_all_positions(self.end_date)

        self.logger.info("回测完成！")
        self._print_summary()

        return True

    def _process_buy_signal(self, signal: TradeSignal, date: str):
        """
        处理买入信号

        Args:
            signal: 交易信号
            date: 当前日期
        """
        # 获取股票数据
        df = self.data_query.daily_with_indicators(
            signal.ts_code,
            start_date=(datetime.strptime(date, '%Y%m%d') - timedelta(days=60)).strftime('%Y%m%d'),
            end_date=date
        )

        if df is None or df.empty:
            self.logger.warning(f"无法获取 {signal.ts_code} 的数据")
            return

        # 获取当前日期的数据
        current_data = df[df['trade_date'] == date]
        if current_data.empty:
            self.logger.warning(f"{signal.ts_code} 在 {date} 无交易数据")
            return

        # 检查是否已经持仓
        if signal.ts_code in self.portfolio.positions:
            self.logger.info(f"{signal.ts_code} 已持仓，跳过买入信号")
            return

        # 调用策略判断是否买入
        if not self.strategy.should_buy(
            ts_code=signal.ts_code,
            date=date,
            data=df,
            portfolio_value=self.portfolio.get_total_value()
        ):
            return

        # 计算买入金额
        buy_amount = self.strategy.calculate_position_size(
            ts_code=signal.ts_code,
            date=date,
            data=df,
            available_cash=self.portfolio.cash,
            signal_ratio=signal.position_ratio
        )

        # 使用开盘价买入（或收盘价）
        buy_price = current_data.iloc[0]['open'] if 'open' in current_data.columns else current_data.iloc[0]['close']

        # 执行买入
        self.portfolio.buy(
            ts_code=signal.ts_code,
            price=buy_price,
            amount=buy_amount,
            date=date
        )

    def _update_and_check_sell(self, date: str):
        """
        更新持仓价格并检查是否需要卖出

        Args:
            date: 当前日期
        """
        positions_to_sell = []

        for ts_code, position in self.portfolio.positions.items():
            # 获取当前价格
            df = self.data_query.daily(ts_code, start_date=date, end_date=date)

            if df is None or df.empty:
                continue

            current_price = df.iloc[0]['close']

            # 更新持仓价格
            self.portfolio.update_positions({ts_code: current_price}, date)

            # 获取历史数据用于策略判断
            df_hist = self.data_query.daily_with_indicators(
                ts_code,
                start_date=(datetime.strptime(date, '%Y%m%d') - timedelta(days=60)).strftime('%Y%m%d'),
                end_date=date
            )

            # 调用策略判断是否卖出
            if self.strategy.should_sell(
                ts_code=ts_code,
                date=date,
                data=df_hist if df_hist is not None else df,
                position=position
            ):
                positions_to_sell.append((ts_code, current_price))

        # 执行卖出
        for ts_code, sell_price in positions_to_sell:
            self.portfolio.sell(ts_code, sell_price, date)

    def _close_all_positions(self, date: str):
        """
        强制平仓所有持仓

        Args:
            date: 平仓日期
        """
        if not self.portfolio.positions:
            return

        self.logger.info(f"回测结束，强制平仓 {len(self.portfolio.positions)} 个持仓")

        positions_to_close = list(self.portfolio.positions.keys())
        for ts_code in positions_to_close:
            # 获取最后价格
            df = self.data_query.daily(ts_code, start_date=date, end_date=date)
            if df is not None and not df.empty:
                close_price = df.iloc[0]['close']
            else:
                # 如果无法获取价格，使用持仓的当前价格
                close_price = self.portfolio.positions[ts_code].current_price

            self.portfolio.sell(ts_code, close_price, date, notes="回测结束强制平仓")

    def _print_summary(self):
        """打印回测摘要"""
        total_return = self.portfolio.get_return_rate()
        final_value = self.portfolio.get_total_value()

        print("\n" + "=" * 60)
        print("回测结果摘要")
        print("=" * 60)
        print(f"初始资金：{self.initial_capital:,.2f}")
        print(f"最终资金：{final_value:,.2f}")
        print(f"总收益：{final_value - self.initial_capital:,.2f}")
        print(f"总收益率：{total_return:.2%}")
        print(f"总交易次数：{self.portfolio.total_trades}")
        print(f"总手续费：{self.portfolio.total_commission:,.2f}")
        print(f"已平仓交易：{len(self.portfolio.closed_positions)}")
        print(f"策略：{self.strategy}")
        print("=" * 60 + "\n")

    def get_results(self) -> dict:
        """
        获取回测结果

        Returns:
            包含所有回测结果的字典
        """
        return {
            'portfolio': self.portfolio,
            'equity_curve': pd.DataFrame(self.portfolio.equity_curve),
            'trades': pd.DataFrame(self.portfolio.get_trades_summary()),
            'positions': pd.DataFrame(self.portfolio.get_positions_summary()) if self.portfolio.positions else pd.DataFrame(),
            'initial_capital': self.initial_capital,
            'final_value': self.portfolio.get_total_value(),
            'total_return': self.portfolio.get_return_rate(),
            'strategy': self.strategy.get_params()
        }
