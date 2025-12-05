#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
首板放量涨停板筛选与溢价统计工具

功能：
1. 在指定日期范围内扫描股票池
2. 筛选符合条件的首板放量涨停板
3. 统计下一交易日的三种溢价
4. 生成CSV详细数据和TXT统计报告

筛选条件：
1. 首板放量板：涨停板（10%或20%）+ 成交量超过前一日2倍 + 首板
2. 半年内高点限制：(半年最高价 - 当前价) / 当前价 <= 30%
3. 一个月内跌幅限制：(一个月最高价 - 当前价) / 一个月最高价 <= 10%
4. 近4天无连续阳线
5. 近4天无连续阴线

溢价统计：
1. 下一日收盘溢价：(下一日收盘 - 选中日收盘) / 选中日收盘
2. 下一日日内涨跌幅：(下一日收盘 - 下一日开盘) / 下一日开盘
3. 下一日最高价溢价：(下一日最高 - 选中日收盘) / 选中日收盘

使用示例：
python scripts/first_limit_premium_scanner.py --start-date 20241101 --end-date 20241130
"""

import os
import sys
import logging
import argparse
import pandas as pd
import yaml
import warnings
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

warnings.filterwarnings('ignore')

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入数据库模块
from database.query_helper import StockDataQuery

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def calculate_data_range(scan_start: str, scan_end: str) -> Tuple[str, str]:
    """
    计算数据查询范围

    Args:
        scan_start: 扫描开始日期 YYYYMMDD
        scan_end: 扫描结束日期 YYYYMMDD

    Returns:
        (数据查询开始日期, 数据查询结束日期)
    """
    scan_start_dt = datetime.strptime(scan_start, '%Y%m%d')
    scan_end_dt = datetime.strptime(scan_end, '%Y%m%d')

    # 向前210天（半年180天+缓冲30天）
    data_start_dt = scan_start_dt - timedelta(days=210)
    # 向后6天（下一交易日+缓冲）
    data_end_dt = scan_end_dt + timedelta(days=6)

    return data_start_dt.strftime('%Y%m%d'), data_end_dt.strftime('%Y%m%d')


class FirstLimitPremiumScanner:
    """首板放量涨停板扫描器"""

    def __init__(self, config: dict):
        """
        初始化扫描器

        Args:
            config: 配置参数字典
        """
        self.config = config
        self.query = StockDataQuery()
        self.stock_names = {}  # 股票代码->名称映射
        logger.info("✓ 首板放量涨停板扫描器已初始化")

    def load_stock_pool(self, pool_file: str) -> List[Dict]:
        """
        加载股票池

        Args:
            pool_file: 股票池文件路径

        Returns:
            股票列表 [{'ts_code': 'xxx', 'name': 'xxx'}]
        """
        stock_list = []

        if not os.path.exists(pool_file):
            logger.error(f"股票池文件不存在: {pool_file}")
            return stock_list

        try:
            with open(pool_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # 支持多种格式
                    # 688256.SH # 寒武纪
                    # 688256.SH
                    if '#' in line:
                        parts = line.split('#')
                        ts_code = parts[0].strip()
                        name = parts[1].strip() if len(parts) > 1 else ''
                    else:
                        parts = line.replace(',', ' ').split()
                        ts_code = parts[0]
                        name = parts[1] if len(parts) > 1 else ''

                    stock_list.append({'ts_code': ts_code, 'name': name})
                    self.stock_names[ts_code] = name

            logger.info(f"✓ 加载股票池: {pool_file} (共{len(stock_list)}只)")
        except Exception as e:
            logger.error(f"加载股票池失败: {e}")

        return stock_list

    def determine_limit_threshold(self, ts_code: str) -> float:
        """
        判断涨停板阈值

        Args:
            ts_code: 股票代码

        Returns:
            涨停阈值（9.95表示10%，19.95表示20%）
        """
        # 科创板（688xxx.SH）
        if ts_code.startswith('688') and ts_code.endswith('.SH'):
            return 19.95

        # 创业板（300xxx.SZ）
        if ts_code.startswith('300') and ts_code.endswith('.SZ'):
            return 19.95

        # 北交所（8xxxxx.BJ）
        if ts_code.startswith('8') and ts_code.endswith('.BJ'):
            return 29.95

        # 主板及其他
        return 9.95

    def is_limit_up(self, row: pd.Series, ts_code: str, tolerance: float = 0.05) -> bool:
        """
        判断是否为涨停板

        Args:
            row: 单日数据
            ts_code: 股票代码
            tolerance: 容差

        Returns:
            True表示涨停
        """
        threshold = self.determine_limit_threshold(ts_code)
        pct_chg = row['pct_chg']
        return pct_chg >= (threshold - tolerance)

    def is_first_board(self, df: pd.DataFrame, idx: int, ts_code: str) -> bool:
        """
        判断是否为首板（前一日未涨停）

        Args:
            df: 完整数据
            idx: 当前行索引
            ts_code: 股票代码

        Returns:
            True表示首板
        """
        if idx == 0:
            return True

        prev_row = df.iloc[idx - 1]
        return not self.is_limit_up(prev_row, ts_code)

    def check_volume_condition(self, row: pd.Series, prev_row: pd.Series) -> bool:
        """
        检查放量条件

        Args:
            row: 当日数据
            prev_row: 前一日数据

        Returns:
            True表示满足放量条件
        """
        volume_multiple = self.config.get('volume_multiple', 3.0)

        if prev_row['vol'] == 0:
            return False

        return row['vol'] >= prev_row['vol'] * volume_multiple

    def check_half_year_high(self, df: pd.DataFrame, idx: int,
                            current_price: float) -> Tuple[bool, float]:
        """
        检查半年内高点条件

        Args:
            df: 完整数据
            idx: 当前行索引
            current_price: 当前价格

        Returns:
            (是否满足条件, 半年最高价)
        """
        start_idx = max(0, idx - 180)
        half_year_df = df.iloc[start_idx:idx+1]

        if half_year_df.empty:
            return False, 0.0

        half_year_high = half_year_df['high'].max()

        if current_price == 0:
            return False, half_year_high

        # (最高价 - 当前价) / 当前价 <= 30%
        distance_pct = (half_year_high - current_price) / current_price * 100

        return distance_pct <= 30, half_year_high

    def check_one_month_drop(self, df: pd.DataFrame, idx: int,
                            current_price: float) -> Tuple[bool, float]:
        """
        检查一个月内跌幅条件

        Args:
            df: 完整数据
            idx: 当前行索引
            current_price: 当前价格

        Returns:
            (是否满足条件, 一个月最高价)
        """
        start_idx = max(0, idx - 30)
        one_month_df = df.iloc[start_idx:idx+1]

        if one_month_df.empty:
            return False, 0.0

        one_month_high = one_month_df['high'].max()

        if one_month_high == 0:
            return False, one_month_high

        # (一个月最高价 - 当前价) / 一个月最高价 <= 10%
        drop_pct = (one_month_high - current_price) / one_month_high * 100

        return drop_pct <= 10, one_month_high

    def check_no_continuous_candles(self, df: pd.DataFrame, idx: int,
                                   days: int = 4) -> Tuple[bool, bool]:
        """
        检查近N天无连续阳线和连续阴线

        Args:
            df: 完整数据
            idx: 当前行索引
            days: 检查天数

        Returns:
            (无连续阳线, 无连续阴线) - True表示通过条件
        """
        start_idx = max(0, idx - days + 1)
        recent_df = df.iloc[start_idx:idx+1]

        if len(recent_df) < days:
            # 数据不足，默认通过
            return True, True

        # 判断阳线（收盘价 > 开盘价）和阴线（收盘价 < 开盘价）
        is_yang = (recent_df['close'] > recent_df['open']).tolist()
        is_yin = (recent_df['close'] < recent_df['open']).tolist()

        # 检查是否全是阳线或全是阴线
        all_yang = all(is_yang)
        all_yin = all(is_yin)

        no_continuous_yang = not all_yang
        no_continuous_yin = not all_yin

        return no_continuous_yang, no_continuous_yin

    def calculate_premiums(self, selected_row: pd.Series,
                          next_row: pd.Series) -> Dict[str, float]:
        """
        计算三种溢价

        Args:
            selected_row: 选中日数据
            next_row: 下一交易日数据

        Returns:
            包含三种溢价的字典
        """
        selected_close = selected_row['close']
        next_open = next_row['open']
        next_close = next_row['close']
        next_high = next_row['high']

        # 1. 相对于选中日收盘价的溢价
        premium_close = ((next_close - selected_close) / selected_close * 100) if selected_close != 0 else 0

        # 2. 下一日日内涨跌幅
        premium_intraday = ((next_close - next_open) / next_open * 100) if next_open != 0 else 0

        # 3. 相对于选中日收盘价到下一日最高价
        premium_high = ((next_high - selected_close) / selected_close * 100) if selected_close != 0 else 0

        return {
            'next_close_premium': round(premium_close, 2),
            'next_intraday_premium': round(premium_intraday, 2),
            'next_high_premium': round(premium_high, 2)
        }

    def scan_single_stock(self, ts_code: str, stock_name: str,
                         scan_start: str, scan_end: str) -> List[Dict]:
        """
        扫描单只股票

        Args:
            ts_code: 股票代码
            stock_name: 股票名称
            scan_start: 扫描开始日期
            scan_end: 扫描结束日期

        Returns:
            符合条件的记录列表
        """
        results = []

        # 计算数据查询范围
        data_start, data_end = calculate_data_range(scan_start, scan_end)

        # 获取数据
        df = self.query.daily(ts_code, data_start, data_end)

        if df is None or df.empty:
            logger.warning(f"  {ts_code} 无数据")
            return results

        # 确保按日期升序排序
        df = df.sort_values('trade_date', ascending=True).reset_index(drop=True)

        # 添加日期字符串列（用于过滤）
        df['trade_date_str'] = df['trade_date'].astype(str).str.replace('-', '')

        # 过滤扫描日期范围内的索引
        scan_indices = df[
            (df['trade_date_str'] >= scan_start) &
            (df['trade_date_str'] <= scan_end)
        ].index.tolist()

        # 遍历扫描范围内的每一天
        for idx in scan_indices:
            row = df.iloc[idx]

            # 价格过滤
            min_price = self.config.get('min_price', 3.0)
            max_price = self.config.get('max_price', 500.0)
            if row['close'] < min_price or row['close'] > max_price:
                continue

            # 1. 检查是否涨停
            if not self.is_limit_up(row, ts_code):
                continue

            # 2. 检查是否首板
            if not self.is_first_board(df, idx, ts_code):
                continue

            # 3. 检查放量条件（需要前一日数据）
            if idx == 0:
                continue
            prev_row = df.iloc[idx - 1]
            if not self.check_volume_condition(row, prev_row):
                continue

            # 4. 检查半年内高点条件
            half_year_ok, half_year_high = self.check_half_year_high(df, idx, row['close'])
            if not half_year_ok:
                continue

            # 5. 检查一个月内跌幅条件
            one_month_ok, one_month_high = self.check_one_month_drop(df, idx, row['close'])
            if not one_month_ok:
                continue

            # 6. 检查无连续阳线和阴线
            no_yang, no_yin = self.check_no_continuous_candles(df, idx, days=4)
            if not (no_yang and no_yin):
                continue

            # ✅ 通过所有筛选条件

            # 获取下一个交易日数据
            next_row = None
            if idx + 1 < len(df):
                next_row = df.iloc[idx + 1]

            # 获取下下个交易日数据（用于计算买入卖出收益）
            next_next_row = None
            if idx + 2 < len(df):
                next_next_row = df.iloc[idx + 2]

            # 计算溢价
            if next_row is not None:
                premiums = self.calculate_premiums(row, next_row)
            else:
                premiums = {
                    'next_close_premium': None,
                    'next_intraday_premium': None,
                    'next_high_premium': None
                }

            # 计算买入卖出收益
            # 策略：第二个交易日（下一日）开盘买入，第三个交易日（下下个交易日）开盘卖出
            trade_profit = None
            buy_price = None
            sell_price = None
            if next_row is not None and next_next_row is not None:
                buy_price = next_row['open']  # 下一日开盘价买入
                sell_price = next_next_row['open']  # 下下个交易日开盘价卖出
                if buy_price != 0:
                    trade_profit = (sell_price - buy_price) / buy_price * 100  # 收益率
                    trade_profit = round(trade_profit, 2)

            # 获取前后3天的数据（用于详细表格）
            surrounding_data = []
            for offset in range(-3, 4):  # -3, -2, -1, 0, 1, 2, 3
                data_idx = idx + offset
                if 0 <= data_idx < len(df):
                    day_row = df.iloc[data_idx]
                    surrounding_data.append({
                        'offset': offset,
                        'date': day_row['trade_date_str'],
                        'open': round(day_row['open'], 2),
                        'close': round(day_row['close'], 2),
                        'volume': int(day_row['vol']),
                        'is_signal_day': (offset == 0)
                    })

            # 构建结果
            result = {
                'ts_code': ts_code,
                'stock_name': stock_name,
                'selected_date': row['trade_date_str'],
                'selected_close': round(row['close'], 2),
                'selected_volume': int(row['vol']),
                'selected_pct_chg': round(row['pct_chg'], 2),
                'prev_volume': int(prev_row['vol']),
                'volume_ratio': round(row['vol'] / prev_row['vol'], 2) if prev_row['vol'] != 0 else 0,
                'half_year_high': round(half_year_high, 2),
                'half_year_high_distance_pct': round((half_year_high - row['close']) / row['close'] * 100, 2) if row['close'] != 0 else 0,
                'one_month_high': round(one_month_high, 2),
                'one_month_drop_pct': round((one_month_high - row['close']) / one_month_high * 100, 2) if one_month_high != 0 else 0,
                'next_trade_date': next_row['trade_date_str'] if next_row is not None else None,
                'next_open': round(next_row['open'], 2) if next_row is not None else None,
                'next_close': round(next_row['close'], 2) if next_row is not None else None,
                'next_high': round(next_row['high'], 2) if next_row is not None else None,
                'next_next_trade_date': next_next_row['trade_date_str'] if next_next_row is not None else None,
                'next_next_open': round(next_next_row['open'], 2) if next_next_row is not None else None,
                'buy_price': round(buy_price, 2) if buy_price is not None else None,
                'sell_price': round(sell_price, 2) if sell_price is not None else None,
                'trade_profit': trade_profit,  # 交易收益率
                'surrounding_data': surrounding_data,  # 前后3天数据
                **premiums
            }

            results.append(result)

        return results

    def scan_batch(self, stock_list: List[Dict],
                   scan_start: str, scan_end: str,
                   test_mode: bool = False) -> pd.DataFrame:
        """
        批量扫描

        Args:
            stock_list: 股票列表
            scan_start: 扫描开始日期
            scan_end: 扫描结束日期
            test_mode: 测试模式

        Returns:
            结果DataFrame
        """
        if test_mode:
            stock_list = stock_list[:10]
            logger.warning(f"⚠️  测试模式：仅扫描前{len(stock_list)}只股票")

        all_results = []
        total = len(stock_list)

        logger.info("=" * 80)
        logger.info(f"开始批量扫描：共{total}只股票")
        logger.info(f"扫描日期范围: {scan_start} 至 {scan_end}")
        logger.info("=" * 80)

        for i, stock in enumerate(stock_list, 1):
            ts_code = stock['ts_code']
            name = stock.get('name', '')

            logger.info(f"[{i}/{total}] {ts_code} {name}")

            try:
                results = self.scan_single_stock(ts_code, name, scan_start, scan_end)
                if results:
                    all_results.extend(results)
                    logger.info(f"  ★ 发现{len(results)}条符合条件的记录")
            except Exception as e:
                logger.error(f"  ✗ 扫描出错: {e}")

        logger.info("=" * 80)
        logger.info(f"扫描完成：共发现{len(all_results)}条符合条件的记录")
        logger.info("=" * 80)

        # 转换为DataFrame
        if all_results:
            results_df = pd.DataFrame(all_results)
        else:
            results_df = pd.DataFrame()

        return results_df

    def generate_reports(self, results_df: pd.DataFrame, output_dir: str):
        """
        生成报告（仅生成信号详细表格）

        Args:
            results_df: 结果DataFrame
            output_dir: 输出目录
        """
        # 创建输出目录
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logger.info(f"创建输出目录: {output_dir}")

        # 时间戳
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 生成信号详细表格（前后3天数据）
        detail_table_file = f'signal_detail_table_{timestamp}.txt'
        detail_table_path = os.path.join(output_dir, detail_table_file)
        self.generate_signal_detail_table(results_df, detail_table_path)
        logger.info(f"✓ 信号详细表格已保存: {detail_table_path}")

    def generate_signal_detail_table(self, results_df: pd.DataFrame, output_path: str):
        """
        生成信号详细表格（包含前后3天的收盘价和成交量，以及交易收益统计）

        Args:
            results_df: 结果DataFrame
            output_path: 输出文件路径
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 100 + "\n")
            f.write(" " * 20 + "首板放量涨停板信号 - 前后3天详细数据表及交易收益统计\n")
            f.write("=" * 100 + "\n\n")

            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"共 {len(results_df)} 个交易信号\n")
            f.write(f"交易策略: 第二个交易日开盘买入，第三个交易日开盘卖出\n")
            f.write("\n")

            # 统计变量
            valid_trades = []

            # 遍历每个信号
            for idx, row in results_df.iterrows():
                f.write("=" * 100 + "\n")
                f.write(f"信号 #{idx + 1}\n")
                f.write(f"股票代码: {row['ts_code']:12s}  股票名称: {row['stock_name']:10s}  触发日期: {row['selected_date']}\n")
                f.write(f"涨停幅度: {row['selected_pct_chg']:+.2f}%  放量倍数: {row['volume_ratio']:.2f}x\n")
                f.write("-" * 100 + "\n")

                # 表头
                f.write(f"{'日期':12s}  {'开盘价':>10s}  {'收盘价':>10s}  {'成交量':>15s}  {'说明':20s}\n")
                f.write("-" * 100 + "\n")

                # 前后3天数据
                surrounding_data = row.get('surrounding_data', [])
                if surrounding_data:
                    for day_data in surrounding_data:
                        date = day_data['date']
                        open_price = day_data['open']
                        close = day_data['close']
                        volume = day_data['volume']
                        is_signal = day_data['is_signal_day']

                        # 格式化成交量（添加千位分隔符）
                        volume_str = f"{volume:,}"

                        # 标记信号日
                        marker = "  ★ 触发信号日" if is_signal else ""

                        f.write(f"{date:12s}  {open_price:>10.2f}  {close:>10.2f}  {volume_str:>15s}{marker}\n")
                else:
                    f.write("（无前后3天数据）\n")

                # 交易收益统计
                f.write("-" * 100 + "\n")
                f.write(f"【交易收益统计】\n")

                trade_profit = row.get('trade_profit')
                if trade_profit is not None:
                    buy_price = row['buy_price']
                    sell_price = row['sell_price']
                    buy_date = row['next_trade_date']
                    sell_date = row['next_next_trade_date']

                    profit_marker = "✓" if trade_profit > 0 else "✗"

                    f.write(f"  买入: {buy_date} 开盘价 {buy_price:.2f}元\n")
                    f.write(f"  卖出: {sell_date} 开盘价 {sell_price:.2f}元\n")
                    f.write(f"  收益率: {trade_profit:+.2f}% {profit_marker}\n")

                    # 记录有效交易
                    valid_trades.append(trade_profit)
                else:
                    f.write(f"  （无法计算交易收益，缺少第二或第三个交易日数据）\n")

                # 溢价信息
                if row['next_close_premium'] is not None:
                    f.write(f"\n【下一日溢价参考】\n")
                    f.write(f"  收盘溢价: {row['next_close_premium']:+.2f}%  |  ")
                    f.write(f"日内涨跌: {row['next_intraday_premium']:+.2f}%  |  ")
                    f.write(f"最高溢价: {row['next_high_premium']:+.2f}%\n")

                f.write("\n")

            # 总体盈亏统计
            f.write("=" * 100 + "\n")
            f.write("【总体盈亏统计】\n")
            f.write("=" * 100 + "\n")

            if valid_trades:
                total_signals = len(results_df)
                valid_count = len(valid_trades)

                # 盈利和亏损统计
                profit_trades = [p for p in valid_trades if p > 0]
                loss_trades = [p for p in valid_trades if p < 0]
                breakeven_trades = [p for p in valid_trades if p == 0]

                profit_count = len(profit_trades)
                loss_count = len(loss_trades)
                breakeven_count = len(breakeven_trades)

                # 胜率
                win_rate = (profit_count / valid_count * 100) if valid_count > 0 else 0

                # 平均收益
                avg_profit = sum(valid_trades) / valid_count if valid_count > 0 else 0
                avg_profit_win = sum(profit_trades) / profit_count if profit_count > 0 else 0
                avg_profit_loss = sum(loss_trades) / loss_count if loss_count > 0 else 0

                # 总收益
                total_profit = sum(valid_trades)

                # 最大单笔盈亏
                max_profit = max(valid_trades) if valid_trades else 0
                max_loss = min(valid_trades) if valid_trades else 0

                f.write(f"\n信号总数: {total_signals} 个\n")
                f.write(f"有效交易数: {valid_count} 笔（有完整买入卖出数据）\n")
                f.write(f"无效交易数: {total_signals - valid_count} 笔（缺少数据）\n")
                f.write("\n")

                f.write(f"盈利交易: {profit_count} 笔\n")
                f.write(f"亏损交易: {loss_count} 笔\n")
                f.write(f"持平交易: {breakeven_count} 笔\n")
                f.write("\n")

                f.write(f"胜率: {win_rate:.2f}%\n")
                f.write("\n")

                f.write(f"累计总收益率: {total_profit:+.2f}%\n")
                f.write(f"平均收益率: {avg_profit:+.2f}%\n")
                f.write(f"平均盈利收益率: {avg_profit_win:+.2f}% （仅盈利交易）\n")
                f.write(f"平均亏损收益率: {avg_profit_loss:+.2f}% （仅亏损交易）\n")
                f.write("\n")

                f.write(f"最大单笔盈利: {max_profit:+.2f}%\n")
                f.write(f"最大单笔亏损: {max_loss:+.2f}%\n")
                f.write("\n")

                # 盈亏比
                if loss_count > 0 and avg_profit_loss != 0:
                    profit_loss_ratio = abs(avg_profit_win / avg_profit_loss)
                    f.write(f"盈亏比: {profit_loss_ratio:.2f} （平均盈利/平均亏损）\n")
                    f.write("\n")

                # 评估
                f.write("【策略评估】\n")
                if total_profit > 0:
                    f.write(f"✓ 该策略在测试期间整体盈利，累计收益率 {total_profit:+.2f}%\n")
                else:
                    f.write(f"✗ 该策略在测试期间整体亏损，累计收益率 {total_profit:+.2f}%\n")

                if win_rate >= 50:
                    f.write(f"✓ 胜率较高（{win_rate:.2f}%），多数交易盈利\n")
                else:
                    f.write(f"✗ 胜率较低（{win_rate:.2f}%），多数交易亏损\n")

            else:
                f.write("\n无有效交易数据可统计\n")

            f.write("\n")
            f.write("=" * 100 + "\n")


def load_config(config_file: str) -> dict:
    """
    从YAML文件加载配置

    Args:
        config_file: 配置文件路径

    Returns:
        配置字典
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"✓ 配置文件加载成功: {config_file}")
        return config
    except FileNotFoundError:
        logger.error(f"配置文件不存在: {config_file}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"配置文件格式错误: {e}")
        return {}


def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(
        description='首板放量涨停板筛选与溢价统计工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  # 使用配置文件运行
  python scripts/first_limit_premium_scanner.py --config config/first_limit_scanner_config.yaml

  # 使用配置文件，但覆盖日期参数
  python scripts/first_limit_premium_scanner.py --config config/first_limit_scanner_config.yaml --start-date 20241201

  # 传统命令行方式（不使用配置文件）
  python scripts/first_limit_premium_scanner.py --start-date 20241101 --end-date 20241130
        """
    )

    # 配置文件参数
    parser.add_argument('--config', type=str,
                       help='配置文件路径（YAML格式），如使用配置文件则其他参数可选')

    # 日期参数
    parser.add_argument('--start-date', type=str,
                       help='扫描开始日期，格式YYYYMMDD')
    parser.add_argument('--end-date', type=str,
                       help='扫描结束日期，格式YYYYMMDD')

    # 可选参数
    parser.add_argument('--pool', type=str,
                       help='股票池文件路径')
    parser.add_argument('--use-local-db', action='store_true',
                       help='使用本地数据库')
    parser.add_argument('--output-dir', type=str,
                       help='输出目录')
    parser.add_argument('--min-price', type=float,
                       help='最低价格过滤（元）')
    parser.add_argument('--max-price', type=float,
                       help='最高价格过滤（元）')
    parser.add_argument('--volume-multiple', type=float,
                       help='放量倍数')
    parser.add_argument('--test', action='store_true',
                       help='测试模式（仅扫描前10只股票）')
    parser.add_argument('--verbose', action='store_true',
                       help='详细输出模式')

    args = parser.parse_args()

    # 加载配置文件（如果指定）
    file_config = {}
    if args.config:
        file_config = load_config(args.config)
        if not file_config:
            logger.error("无法加载配置文件，退出")
            sys.exit(1)

    # 合并配置：命令行参数优先级高于配置文件
    start_date = args.start_date or (file_config.get('date_range', {}).get('start_date') if file_config else None)
    end_date = args.end_date or (file_config.get('date_range', {}).get('end_date') if file_config else None)

    if not start_date or not end_date:
        logger.error("必须指定扫描日期范围（通过配置文件或命令行参数）")
        parser.print_help()
        sys.exit(1)

    # 其他参数
    pool_file = args.pool or (file_config.get('data_source', {}).get('stock_pool') if file_config else None) or 'pool/stock_pool_all.txt'
    output_dir = args.output_dir or (file_config.get('output', {}).get('output_dir') if file_config else None) or 'first_limit_premium_results'

    filter_config = file_config.get('filter_conditions', {}) if file_config else {}
    min_price = args.min_price if args.min_price is not None else filter_config.get('min_price', 3.0)
    max_price = args.max_price if args.max_price is not None else filter_config.get('max_price', 500.0)
    volume_multiple = args.volume_multiple if args.volume_multiple is not None else filter_config.get('volume_multiple', 2.0)

    run_mode_config = file_config.get('run_mode', {}) if file_config else {}
    test_mode = args.test or run_mode_config.get('test_mode', False)
    verbose = args.verbose or run_mode_config.get('verbose', False)

    # 设置日志级别
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 配置参数
    config = {
        'min_price': min_price,
        'max_price': max_price,
        'volume_multiple': volume_multiple,
    }

    # 初始化扫描器
    logger.info("=" * 80)
    logger.info("首板放量涨停板筛选与溢价统计工具")
    if file_config and file_config.get('notes'):
        logger.info(f"配置: {file_config['notes'].strip().split(chr(10))[0]}")
    logger.info("=" * 80)

    scanner = FirstLimitPremiumScanner(config)

    # 加载股票池
    stock_list = scanner.load_stock_pool(pool_file)
    if not stock_list:
        logger.error("股票池为空，退出")
        sys.exit(1)

    # 批量扫描
    results_df = scanner.scan_batch(
        stock_list,
        start_date,
        end_date,
        test_mode=test_mode
    )

    # 生成报告
    if not results_df.empty:
        scanner.generate_reports(results_df, output_dir)

        logger.info("=" * 80)
        logger.info(f"✅ 扫描完成！共发现 {len(results_df)} 条符合条件的记录")
        logger.info(f"📄 信号详细表格已保存到: {output_dir}/")
        logger.info("=" * 80)

        # 输出简要统计
        valid_trades = [row['trade_profit'] for _, row in results_df.iterrows() if row.get('trade_profit') is not None]
        if valid_trades:
            profit_count = sum(1 for p in valid_trades if p > 0)
            win_rate = (profit_count / len(valid_trades) * 100) if valid_trades else 0
            total_profit = sum(valid_trades)

            logger.info("\n简要统计:")
            logger.info(f"  有效交易数: {len(valid_trades)} 笔")
            logger.info(f"  胜率: {win_rate:.2f}%")
            logger.info(f"  累计收益率: {total_profit:+.2f}%")
            logger.info(f"  平均收益率: {total_profit / len(valid_trades):+.2f}%")
    else:
        logger.info("=" * 80)
        logger.info("未发现符合条件的记录")
        logger.info("=" * 80)


if __name__ == '__main__':
    main()
