#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
低位缩量反转策略 - 回测工具

功能：
1. 对历史数据进行滚动窗口回测
2. 模拟信号触发后的交易执行
3. 统计策略的胜率、盈亏比、收益率等指标
4. 生成详细的回测报告

使用示例：
1. 回测单只股票（最近1年）：
   python low_volume_backtest.py --code 688256.SH --name 寒武纪

2. 回测指定时间段：
   python low_volume_backtest.py --code 688256.SH --start 20240101 --end 20251110

3. 批量回测股票池：
   python low_volume_backtest.py --pool pool/stock_pool_small.txt --start 20240101
"""

import os
import sys
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import warnings

warnings.filterwarnings('ignore')

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入依赖
from strategies.low_volume_reversal_strategy import LowVolumeReversalStrategy
from database.db_manager import StockDatabase
from config.low_volume_reversal_config import BACKTEST_CONFIG, RISK_MANAGEMENT

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# 输出目录
OUTPUT_DIR = 'low_volume_reports'
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)


class LowVolumeBacktest:
    """低位缩量反转策略回测工具"""

    def __init__(self):
        """初始化回测工具"""
        self.strategy = LowVolumeReversalStrategy()
        self.db = StockDatabase()

    def backtest_single_stock(self, ts_code: str, stock_name: str = '',
                             start_date: str = None, end_date: str = None) -> Dict:
        """
        回测单只股票

        Args:
            ts_code: 股票代码
            stock_name: 股票名称
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）

        Returns:
            回测结果字典
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"回测: {ts_code} {stock_name}")
        logger.info(f"{'='*80}")

        # 设置默认日期范围
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        if start_date is None:
            start_date = (datetime.strptime(end_date, '%Y%m%d') -
                         timedelta(days=BACKTEST_CONFIG.get('default_lookback_days', 365))).strftime('%Y%m%d')

        # 获取全部数据（需要更早的数据来计算指标）
        data_start = (datetime.strptime(start_date, '%Y%m%d') - timedelta(days=90)).strftime('%Y%m%d')
        df_full = self.db.get_daily_ohlcv(ts_code, data_start, end_date)

        if df_full is None or df_full.empty:
            logger.warning(f"无数据")
            return None

        # 添加必要指标
        df_full = self._add_indicators(df_full)

        # 滚动窗口扫描历史信号
        logger.info(f"滚动窗口扫描历史信号...")
        historical_signals = self._rolling_scan(df_full, ts_code, stock_name, start_date, end_date)

        if not historical_signals:
            logger.info(f"未找到历史信号")
            return None

        logger.info(f"✓ 找到{len(historical_signals)}个历史信号")

        # 模拟交易
        logger.info(f"模拟交易执行...")
        trades = self._simulate_trades(df_full, historical_signals)

        # 统计分析
        stats = self._calculate_stats(trades, ts_code, stock_name, start_date, end_date)

        return stats

    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加必要的技术指标"""
        import pandas_ta as ta

        # volume_multiple
        df['volume_multiple'] = df['vol'] / df['vol'].rolling(window=20).mean()

        # RSI
        if 'RSI' not in df.columns:
            df['RSI'] = ta.rsi(df['close'], length=14)

        # 布林带
        if 'BOLL_Lower' not in df.columns:
            bbands = ta.bbands(df['close'], length=20, std=2)
            if bbands is not None:
                df['BOLL_Lower'] = bbands.iloc[:, 0]
                df['BOLL_Mid'] = bbands.iloc[:, 1]
                df['BOLL_Upper'] = bbands.iloc[:, 2]

        # 均线
        for period in [20, 60]:
            col = f'MA{period}'
            if col not in df.columns:
                df[col] = ta.sma(df['close'], length=period)

        return df

    def _rolling_scan(self, df: pd.DataFrame, ts_code: str, stock_name: str,
                     start_date: str, end_date: str) -> List[Dict]:
        """滚动窗口扫描历史信号"""
        signals = []

        # 转换日期为datetime
        df['trade_date_dt'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
        start_dt = pd.to_datetime(start_date, format='%Y%m%d')
        end_dt = pd.to_datetime(end_date, format='%Y%m%d')

        # 找到回测期间的数据索引
        backtest_df = df[(df['trade_date_dt'] >= start_dt) & (df['trade_date_dt'] <= end_dt)]

        for idx in range(len(df)):
            current_date = df.iloc[idx]['trade_date_dt']

            # 只在回测期间查找信号
            if current_date < start_dt or current_date > end_dt:
                continue

            # 获取截至当前日期的数据窗口（90天）
            if idx < 90:
                continue

            window_df = df.iloc[max(0, idx-90):idx+1].copy()

            # 执行策略扫描
            try:
                sigs = self.strategy.scan_entry_signals(window_df, ts_code=ts_code, stock_name=stock_name)
                if sigs:
                    # 记录信号触发时的索引
                    for sig in sigs:
                        sig['trigger_idx'] = idx
                    signals.extend(sigs)
            except Exception as e:
                logger.debug(f"扫描{current_date.strftime('%Y%m%d')}出错: {e}")

        return signals

    def _simulate_trades(self, df: pd.DataFrame, signals: List[Dict]) -> List[Dict]:
        """
        模拟交易执行

        Returns:
            交易列表，每个交易包含入场、出场、收益等信息
        """
        trades = []

        for signal in signals:
            trigger_idx = signal['trigger_idx']

            # 入场：第二天开盘价（next_open策略）
            if trigger_idx + 1 >= len(df):
                continue  # 没有下一天数据

            entry_bar = df.iloc[trigger_idx + 1]
            entry_price = entry_bar['open']
            entry_date = entry_bar['trade_date']

            # 止损止盈价格
            stop_loss = signal['stop_loss']
            target = signal['target']

            # 模拟持仓过程
            exit_info = self._find_exit(df, trigger_idx + 1, entry_price, stop_loss, target)

            if exit_info is None:
                continue

            # 计算收益
            exit_price = exit_info['exit_price']
            pnl_pct = (exit_price - entry_price) / entry_price * 100

            # 扣除费用
            commission_rate = BACKTEST_CONFIG.get('commission_rate', 0.0003)
            slippage_rate = BACKTEST_CONFIG.get('slippage_rate', 0.001)
            fees_pct = (commission_rate + slippage_rate) * 2  # 买卖各一次
            net_pnl_pct = pnl_pct - fees_pct * 100

            trade = {
                'signal': signal,
                'entry_date': entry_date,
                'entry_price': entry_price,
                'exit_date': exit_info['exit_date'],
                'exit_price': exit_price,
                'exit_reason': exit_info['exit_reason'],
                'holding_days': exit_info['holding_days'],
                'pnl_pct': pnl_pct,
                'net_pnl_pct': net_pnl_pct,
                'is_win': net_pnl_pct > 0
            }

            trades.append(trade)

        return trades

    def _find_exit(self, df: pd.DataFrame, entry_idx: int,
                  entry_price: float, stop_loss: float, target: float) -> Dict:
        """
        查找出场点（止损或止盈）

        Returns:
            出场信息字典
        """
        max_holding = BACKTEST_CONFIG.get('max_holding_days', 30)

        for i in range(entry_idx, min(entry_idx + max_holding, len(df))):
            bar = df.iloc[i]

            # 检查是否触及止损
            if bar['low'] <= stop_loss:
                return {
                    'exit_date': bar['trade_date'],
                    'exit_price': stop_loss,
                    'exit_reason': 'STOP_LOSS',
                    'holding_days': i - entry_idx + 1
                }

            # 检查是否触及目标
            if bar['high'] >= target:
                return {
                    'exit_date': bar['trade_date'],
                    'exit_price': target,
                    'exit_reason': 'TARGET',
                    'holding_days': i - entry_idx + 1
                }

        # 超过最大持仓天数，强制出场
        last_bar = df.iloc[min(entry_idx + max_holding - 1, len(df) - 1)]
        return {
            'exit_date': last_bar['trade_date'],
            'exit_price': last_bar['close'],
            'exit_reason': 'TIME_EXIT',
            'holding_days': min(max_holding, len(df) - entry_idx)
        }

    def _calculate_stats(self, trades: List[Dict], ts_code: str, stock_name: str,
                        start_date: str, end_date: str) -> Dict:
        """计算回测统计指标"""
        if not trades:
            return None

        total_trades = len(trades)
        wins = [t for t in trades if t['is_win']]
        losses = [t for t in trades if not t['is_win']]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = win_count / total_trades if total_trades > 0 else 0

        avg_win = np.mean([t['net_pnl_pct'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['net_pnl_pct'] for t in losses]) if losses else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        total_return = sum(t['net_pnl_pct'] for t in trades)
        avg_return = total_return / total_trades

        avg_holding = np.mean([t['holding_days'] for t in trades])

        # 按信号强度分组统计
        strength_stats = {}
        for strength in [3, 2, 1, 0]:
            strength_trades = [t for t in trades if t['signal']['strength'] == strength]
            if strength_trades:
                strength_wins = [t for t in strength_trades if t['is_win']]
                strength_stats[strength] = {
                    'count': len(strength_trades),
                    'win_rate': len(strength_wins) / len(strength_trades),
                    'avg_return': np.mean([t['net_pnl_pct'] for t in strength_trades])
                }

        stats = {
            'ts_code': ts_code,
            'stock_name': stock_name,
            'start_date': start_date,
            'end_date': end_date,
            'total_trades': total_trades,
            'win_count': win_count,
            'loss_count': loss_count,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_return': total_return,
            'avg_return': avg_return,
            'avg_holding_days': avg_holding,
            'strength_stats': strength_stats,
            'trades': trades
        }

        return stats

    def generate_report(self, stats: Dict, output_file: str = None) -> str:
        """生成回测报告"""
        if stats is None:
            return None

        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"backtest_{stats['ts_code'].replace('.', '_')}_{timestamp}.txt"

        output_path = os.path.join(OUTPUT_DIR, output_file)

        with open(output_path, 'w', encoding='utf-8') as f:
            # 标题
            f.write("=" * 100 + "\n")
            f.write(" " * 30 + "低位缩量反转策略 - 回测报告\n")
            f.write("=" * 100 + "\n\n")

            # 基本信息
            f.write(f"股票代码: {stats['ts_code']}\n")
            f.write(f"股票名称: {stats['stock_name']}\n")
            f.write(f"回测区间: {stats['start_date']} 至 {stats['end_date']}\n")
            f.write(f"总交易次数: {stats['total_trades']}次\n\n")

            # 整体表现
            f.write("-" * 100 + "\n")
            f.write("【整体表现】\n")
            f.write("-" * 100 + "\n")
            f.write(f"总收益率: {stats['total_return']:+.2f}%\n")
            f.write(f"平均收益率: {stats['avg_return']:+.2f}%\n")
            f.write(f"胜率: {stats['win_rate']*100:.1f}% ({stats['win_count']}胜 / {stats['total_trades']}次)\n")
            f.write(f"平均盈利: {stats['avg_win']:+.2f}%\n")
            f.write(f"平均亏损: {stats['avg_loss']:+.2f}%\n")
            f.write(f"盈亏比: {stats['profit_factor']:.2f}\n")
            f.write(f"平均持仓天数: {stats['avg_holding_days']:.1f}天\n\n")

            # 按信号强度分析
            if stats['strength_stats']:
                f.write("-" * 100 + "\n")
                f.write("【按信号强度分析】\n")
                f.write("-" * 100 + "\n")
                for strength in sorted(stats['strength_stats'].keys(), reverse=True):
                    s = stats['strength_stats'][strength]
                    f.write(f"强度{strength}级 ({s['count']}次): "
                           f"胜率{s['win_rate']*100:.1f}%, "
                           f"平均收益{s['avg_return']:+.2f}%\n")
                f.write("\n")

            # 交易明细
            f.write("-" * 100 + "\n")
            f.write("【交易明细】\n")
            f.write("-" * 100 + "\n")
            f.write(f"{'日期':<12}{'入场价':<10}{'出场价':<10}{'收益率':<10}{'持仓天数':<10}{'出场原因':<15}{'结果'}\n")
            f.write("-" * 100 + "\n")

            for trade in stats['trades']:
                result_icon = "✓" if trade['is_win'] else "✗"
                f.write(f"{trade['entry_date']:<12}"
                       f"{trade['entry_price']:<10.2f}"
                       f"{trade['exit_price']:<10.2f}"
                       f"{trade['net_pnl_pct']:>+8.2f}%  "
                       f"{trade['holding_days']:<10}天"
                       f"{trade['exit_reason']:<15}"
                       f"{result_icon}\n")

            f.write("\n" + "=" * 100 + "\n")

        logger.info(f"✓ 回测报告已保存: {output_path}")
        return output_path


def main():
    """主程序"""
    parser = argparse.ArgumentParser(description='低位缩量反转策略回测工具')

    parser.add_argument('--code', type=str, help='股票代码')
    parser.add_argument('--name', type=str, default='', help='股票名称')
    parser.add_argument('--start', type=str, help='开始日期（YYYYMMDD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYYMMDD）')
    parser.add_argument('--output', type=str, help='输出文件名')

    args = parser.parse_args()

    if not args.code:
        parser.print_help()
        sys.exit(1)

    # 初始化回测工具
    backtest = LowVolumeBacktest()

    # 执行回测
    stats = backtest.backtest_single_stock(args.code, args.name, args.start, args.end)

    if stats:
        # 生成报告
        report_path = backtest.generate_report(stats, args.output)

        logger.info("\n" + "=" * 80)
        logger.info(f"✅ 回测完成！")
        logger.info(f"总交易: {stats['total_trades']}次")
        logger.info(f"胜率: {stats['win_rate']*100:.1f}%")
        logger.info(f"平均收益: {stats['avg_return']:+.2f}%")
        logger.info(f"📄 报告: {report_path}")
        logger.info("=" * 80)
    else:
        logger.info("回测失败或无数据")


if __name__ == '__main__':
    main()
