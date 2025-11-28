"""
可视化模块

生成回测结果的图表
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
import numpy as np
from typing import Optional, List, Dict
from datetime import datetime
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class BacktestVisualizer:
    """
    回测可视化类

    生成各种回测结果图表
    """

    def __init__(self, equity_curve: pd.DataFrame, trades: pd.DataFrame,
                 initial_capital: float):
        """
        初始化可视化器

        Args:
            equity_curve: 净值曲线数据
            trades: 交易记录
            initial_capital: 初始资金
        """
        self.equity_curve = equity_curve.copy()
        self.trades = trades.copy()
        self.initial_capital = initial_capital

        # 转换日期格式
        if not self.equity_curve.empty:
            self.equity_curve['date'] = pd.to_datetime(
                self.equity_curve['date'], format='%Y%m%d'
            )

    def plot_equity_curve(self, save_path: Optional[str] = None, show: bool = True):
        """
        绘制净值曲线

        Args:
            save_path: 保存路径
            show: 是否显示图表
        """
        if self.equity_curve.empty:
            print("没有净值数据")
            return

        fig, ax = plt.subplots(figsize=(12, 6))

        # 绘制总资产曲线
        ax.plot(self.equity_curve['date'], self.equity_curve['total_value'],
               label='总资产', linewidth=2, color='#2E86AB')

        # 绘制基准线（初始资金）
        ax.axhline(y=self.initial_capital, color='gray', linestyle='--',
                  label='初始资金', linewidth=1)

        # 填充盈利/亏损区域
        ax.fill_between(self.equity_curve['date'],
                       self.initial_capital,
                       self.equity_curve['total_value'],
                       where=self.equity_curve['total_value'] >= self.initial_capital,
                       alpha=0.3, color='green', label='盈利区域')
        ax.fill_between(self.equity_curve['date'],
                       self.initial_capital,
                       self.equity_curve['total_value'],
                       where=self.equity_curve['total_value'] < self.initial_capital,
                       alpha=0.3, color='red', label='亏损区域')

        ax.set_xlabel('日期', fontsize=12)
        ax.set_ylabel('资金（元）', fontsize=12)
        ax.set_title('账户净值曲线', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        # 格式化日期
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.xticks(rotation=45)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"净值曲线已保存至：{save_path}")

        if show:
            plt.show()
        else:
            plt.close()

    def plot_drawdown(self, save_path: Optional[str] = None, show: bool = True):
        """
        绘制回撤曲线

        Args:
            save_path: 保存路径
            show: 是否显示图表
        """
        if self.equity_curve.empty:
            print("没有净值数据")
            return

        # 计算回撤
        cum_max = self.equity_curve['total_value'].cummax()
        drawdown = (self.equity_curve['total_value'] - cum_max) / cum_max * 100

        fig, ax = plt.subplots(figsize=(12, 6))

        # 绘制回撤曲线
        ax.fill_between(self.equity_curve['date'], 0, drawdown,
                       alpha=0.5, color='red', label='回撤')
        ax.plot(self.equity_curve['date'], drawdown,
               color='darkred', linewidth=1.5)

        ax.set_xlabel('日期', fontsize=12)
        ax.set_ylabel('回撤 (%)', fontsize=12)
        ax.set_title('账户回撤曲线', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        # 标注最大回撤
        max_dd_idx = drawdown.idxmin()
        max_dd_value = drawdown.min()
        max_dd_date = self.equity_curve.loc[max_dd_idx, 'date']

        ax.annotate(f'最大回撤: {max_dd_value:.2f}%',
                   xy=(max_dd_date, max_dd_value),
                   xytext=(10, 10),
                   textcoords='offset points',
                   bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.7),
                   arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))

        # 格式化日期
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.xticks(rotation=45)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"回撤曲线已保存至：{save_path}")

        if show:
            plt.show()
        else:
            plt.close()

    def plot_monthly_returns(self, save_path: Optional[str] = None, show: bool = True):
        """
        绘制月度收益热力图

        Args:
            save_path: 保存路径
            show: 是否显示图表
        """
        if self.equity_curve.empty:
            print("没有净值数据")
            return

        # 计算月度收益
        df = self.equity_curve.copy()
        df['year'] = df['date'].dt.year
        df['month'] = df['date'].dt.month

        # 每月最后一个交易日的净值
        monthly_value = df.groupby(['year', 'month'])['total_value'].last()
        monthly_returns = monthly_value.pct_change() * 100

        # 重构为矩阵
        years = sorted(df['year'].unique())
        returns_matrix = []

        for year in years:
            year_returns = []
            for month in range(1, 13):
                if (year, month) in monthly_returns.index:
                    year_returns.append(monthly_returns[(year, month)])
                else:
                    year_returns.append(np.nan)
            returns_matrix.append(year_returns)

        returns_matrix = np.array(returns_matrix)

        # 绘制热力图
        fig, ax = plt.subplots(figsize=(12, max(3, len(years) * 0.8)))

        # 使用自定义颜色映射
        cmap = plt.cm.RdYlGn
        im = ax.imshow(returns_matrix, cmap=cmap, aspect='auto',
                      vmin=-10, vmax=10)

        # 设置坐标轴
        ax.set_xticks(np.arange(12))
        ax.set_yticks(np.arange(len(years)))
        ax.set_xticklabels(['1月', '2月', '3月', '4月', '5月', '6月',
                           '7月', '8月', '9月', '10月', '11月', '12月'])
        ax.set_yticklabels(years)

        # 添加数值标签
        for i in range(len(years)):
            for j in range(12):
                if not np.isnan(returns_matrix[i, j]):
                    text = ax.text(j, i, f'{returns_matrix[i, j]:.1f}%',
                                 ha="center", va="center", color="black",
                                 fontsize=9)

        ax.set_title('月度收益率热力图', fontsize=14, fontweight='bold')
        fig.colorbar(im, ax=ax, label='收益率 (%)')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"月度收益图已保存至：{save_path}")

        if show:
            plt.show()
        else:
            plt.close()

    def plot_trade_distribution(self, save_path: Optional[str] = None, show: bool = True):
        """
        绘制交易分布图

        Args:
            save_path: 保存路径
            show: 是否显示图表
        """
        if self.trades.empty:
            print("没有交易记录")
            return

        fig = plt.figure(figsize=(14, 10))
        gs = GridSpec(2, 2, figure=fig)

        # 解析盈亏数据
        if '盈亏' in self.trades.columns:
            pnl = self.trades['盈亏']
        elif 'realized_pnl' in self.trades.columns:
            pnl = self.trades['realized_pnl']
        else:
            print("找不到盈亏数据")
            return

        # 1. 盈亏分布直方图
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.hist(pnl, bins=30, color='skyblue', edgecolor='black', alpha=0.7)
        ax1.axvline(x=0, color='red', linestyle='--', linewidth=2, label='盈亏平衡线')
        ax1.set_xlabel('盈亏（元）', fontsize=11)
        ax1.set_ylabel('交易次数', fontsize=11)
        ax1.set_title('盈亏分布直方图', fontsize=12, fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 2. 盈利vs亏损饼图
        ax2 = fig.add_subplot(gs[0, 1])
        win_count = (pnl > 0).sum()
        loss_count = (pnl < 0).sum()
        break_even = (pnl == 0).sum()

        sizes = [win_count, loss_count, break_even]
        labels = [f'盈利 ({win_count})', f'亏损 ({loss_count})', f'持平 ({break_even})']
        colors = ['#90EE90', '#FFB6C1', '#D3D3D3']
        explode = (0.05, 0.05, 0)

        ax2.pie(sizes, explode=explode, labels=labels, colors=colors,
               autopct='%1.1f%%', shadow=True, startangle=90)
        ax2.set_title('胜率统计', fontsize=12, fontweight='bold')

        # 3. 持仓天数分布
        ax3 = fig.add_subplot(gs[1, 0])
        if '持仓天数' in self.trades.columns:
            hold_days = self.trades['持仓天数']
        elif 'hold_days' in self.trades.columns:
            hold_days = self.trades['hold_days']
        else:
            hold_days = pd.Series([0])

        ax3.hist(hold_days, bins=20, color='lightcoral', edgecolor='black', alpha=0.7)
        ax3.set_xlabel('持仓天数', fontsize=11)
        ax3.set_ylabel('交易次数', fontsize=11)
        ax3.set_title('持仓天数分布', fontsize=12, fontweight='bold')
        ax3.grid(True, alpha=0.3)

        # 4. 累计盈亏曲线
        ax4 = fig.add_subplot(gs[1, 1])
        cumulative_pnl = pnl.cumsum()
        ax4.plot(range(len(cumulative_pnl)), cumulative_pnl,
                linewidth=2, color='#2E86AB')
        ax4.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl,
                        where=cumulative_pnl >= 0, alpha=0.3, color='green')
        ax4.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl,
                        where=cumulative_pnl < 0, alpha=0.3, color='red')
        ax4.set_xlabel('交易序号', fontsize=11)
        ax4.set_ylabel('累计盈亏（元）', fontsize=11)
        ax4.set_title('累计盈亏曲线', fontsize=12, fontweight='bold')
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"交易分布图已保存至：{save_path}")

        if show:
            plt.show()
        else:
            plt.close()

    def plot_all(self, output_dir: str = './backtest_results'):
        """
        生成所有图表并保存

        Args:
            output_dir: 输出目录
        """
        os.makedirs(output_dir, exist_ok=True)

        print("正在生成回测图表...")

        self.plot_equity_curve(
            save_path=os.path.join(output_dir, 'equity_curve.png'),
            show=False
        )

        self.plot_drawdown(
            save_path=os.path.join(output_dir, 'drawdown.png'),
            show=False
        )

        self.plot_monthly_returns(
            save_path=os.path.join(output_dir, 'monthly_returns.png'),
            show=False
        )

        self.plot_trade_distribution(
            save_path=os.path.join(output_dir, 'trade_distribution.png'),
            show=False
        )

        print(f"所有图表已保存至：{output_dir}")
