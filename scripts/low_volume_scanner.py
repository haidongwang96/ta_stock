#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
低位缩量反转策略 - 每日扫描器

功能：
1. 批量扫描股票池，寻找符合条件的入场信号
2. 生成详细的TXT扫描报告
3. 为高质量信号生成K线标注图
4. 支持自定义股票池和参数调整

使用示例：
1. 扫描全部股票池：
   python low_volume_scanner.py --pool pool/stock_pool_all.txt

2. 扫描单只股票并生成图表：
   python low_volume_scanner.py --code 688256.SH --name 寒武纪 --plot

3. 测试模式（仅扫描前10只）：
   python low_volume_scanner.py --pool pool/stock_pool_small.txt --test

4. 使用本地数据库：
   python low_volume_scanner.py --use-local-db
"""

import os
import sys
import logging
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict
import warnings

warnings.filterwarnings('ignore')

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入策略和数据模块
from strategies.low_volume_reversal_strategy import LowVolumeReversalStrategy
from database.db_manager import StockDatabase
from database.query_helper import StockDataQuery
from config.low_volume_reversal_config import SCANNER_CONFIG, DEBUG_CONFIG

# 日志配置
log_level = logging.DEBUG if DEBUG_CONFIG.get('verbose', False) else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 创建输出目录
OUTPUT_DIR = SCANNER_CONFIG.get('output_dir', 'low_volume_reports')
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    logger.info(f"创建输出目录: {OUTPUT_DIR}")


class LowVolumeScanner:
    """低位缩量反转策略扫描器"""

    def __init__(self, use_local_db=True):
        """
        初始化扫描器

        Args:
            use_local_db: 是否使用本地数据库
        """
        self.use_local_db = use_local_db
        self.strategy = LowVolumeReversalStrategy()

        # 初始化数据源
        if use_local_db:
            self.db = StockDatabase()
            self.query = StockDataQuery()
            logger.info("✓ 使用本地数据库")
        else:
            # 使用Tushare（需要token）
            try:
                import tushare as ts
                token_file = os.path.join(project_root, 'token.txt')
                if os.path.exists(token_file):
                    with open(token_file, 'r') as f:
                        token = f.read().strip()
                    ts.set_token(token)
                    self.pro = ts.pro_api()
                    logger.info("✓ 使用Tushare API")
                else:
                    raise FileNotFoundError("token.txt not found")
            except Exception as e:
                logger.error(f"Tushare初始化失败: {e}")
                logger.warning("回退到本地数据库")
                self.use_local_db = True
                self.db = StockDatabase()
                self.query = StockDataQuery()

    def load_stock_pool(self, pool_file: str) -> List[Dict]:
        """
        加载股票池

        Args:
            pool_file: 股票池文件路径

        Returns:
            股票列表，每个元素为 {'ts_code': 'xxx', 'name': 'xxx'}
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

                    # 支持多种格式：
                    # 688256.SH
                    # 688256.SH 寒武纪
                    # 688256.SH,寒武纪
                    parts = line.replace(',', ' ').split()
                    ts_code = parts[0]
                    name = parts[1] if len(parts) > 1 else ''

                    stock_list.append({'ts_code': ts_code, 'name': name})

            logger.info(f"✓ 加载股票池: {pool_file} ({len(stock_list)}只)")
        except Exception as e:
            logger.error(f"加载股票池失败: {e}")

        return stock_list

    def fetch_stock_data(self, ts_code: str, days: int = 90) -> pd.DataFrame:
        """
        获取股票数据

        Args:
            ts_code: 股票代码
            days: 获取天数

        Returns:
            DataFrame
        """
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')

            if self.use_local_db:
                # 从本地数据库获取
                df = self.db.get_combined_data(ts_code, start_date, end_date)
            else:
                # 从Tushare获取
                df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is None or df.empty:
                return None

            # 数据预处理
            df = df.sort_values('trade_date', ascending=True).reset_index(drop=True)

            # 确保有volume_multiple字段
            if 'volume_multiple' not in df.columns:
                if 'vma20' in df.columns:
                    df['volume_multiple'] = df['vol'] / df['vma20']
                else:
                    vma20 = df['vol'].rolling(window=20).mean()
                    df['volume_multiple'] = df['vol'] / vma20

            # 确保有必要的技术指标（如果数据库中没有，临时计算）
            self._ensure_indicators(df)

            return df.tail(days) if len(df) > days else df

        except Exception as e:
            logger.error(f"获取{ts_code}数据失败: {e}")
            return None

    def _ensure_indicators(self, df: pd.DataFrame):
        """确保必要的技术指标存在"""
        import pandas_ta as ta

        # RSI
        if 'RSI' not in df.columns and 'rsi' not in df.columns:
            df['RSI'] = ta.rsi(df['close'], length=14)

        # 布林带
        if 'BOLL_Lower' not in df.columns and 'boll_lower' not in df.columns:
            bbands = ta.bbands(df['close'], length=20, std=2)
            if bbands is not None and not bbands.empty:
                df['BOLL_Lower'] = bbands.iloc[:, 0]
                df['BOLL_Mid'] = bbands.iloc[:, 1]
                df['BOLL_Upper'] = bbands.iloc[:, 2]

        # 均线
        for period in [20, 60]:
            ma_col = f'MA{period}'
            if ma_col not in df.columns and f'ma{period}' not in df.columns:
                df[ma_col] = ta.sma(df['close'], length=period)

    def scan_single_stock(self, ts_code: str, name: str = '') -> List[Dict]:
        """
        扫描单只股票

        Args:
            ts_code: 股票代码
            name: 股票名称

        Returns:
            信号列表
        """
        logger.info(f"扫描: {ts_code} {name}")

        # 获取数据
        df = self.fetch_stock_data(ts_code, days=SCANNER_CONFIG.get('min_data_days', 90))
        if df is None or df.empty:
            logger.warning(f"  无数据")
            return []

        # 过滤条件
        latest = df.iloc[-1]

        # 价格过滤
        min_price = SCANNER_CONFIG.get('min_price', 5.0)
        max_price = SCANNER_CONFIG.get('max_price', 300.0)
        if latest['close'] < min_price or latest['close'] > max_price:
            logger.debug(f"  价格{latest['close']:.2f}不在范围[{min_price}, {max_price}]")
            return []

        # 成交量过滤
        min_volume = SCANNER_CONFIG.get('min_volume', 1000000)
        if latest['vol'] < min_volume:
            logger.debug(f"  成交量{latest['vol']:.0f}低于{min_volume}")
            return []

        # 执行策略扫描
        signals = self.strategy.scan_entry_signals(df, ts_code=ts_code, stock_name=name)

        return signals

    def scan_batch(self, stock_list: List[Dict], test_mode: bool = False) -> List[Dict]:
        """
        批量扫描

        Args:
            stock_list: 股票列表
            test_mode: 测试模式（只扫描前10只）

        Returns:
            所有信号列表
        """
        if test_mode:
            stock_list = stock_list[:10]
            logger.warning(f"⚠️  测试模式：仅扫描前{len(stock_list)}只股票")

        all_signals = []
        total = len(stock_list)

        logger.info("=" * 80)
        logger.info(f"开始批量扫描：共{total}只股票")
        logger.info("=" * 80)

        for i, stock in enumerate(stock_list, 1):
            ts_code = stock['ts_code']
            name = stock.get('name', '')

            logger.info(f"[{i}/{total}] {ts_code} {name}")

            try:
                signals = self.scan_single_stock(ts_code, name)
                if signals:
                    all_signals.extend(signals)
                    logger.info(f"  ★ 发现{len(signals)}个信号")
            except Exception as e:
                logger.error(f"  ✗ 扫描出错: {e}")

        logger.info("=" * 80)
        logger.info(f"扫描完成：共发现{len(all_signals)}个信号")
        logger.info("=" * 80)

        return all_signals

    def generate_report(self, signals: List[Dict], output_file: str = None) -> str:
        """
        生成扫描报告

        Args:
            signals: 信号列表
            output_file: 输出文件名（可选）

        Returns:
            报告文件路径
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"low_volume_scan_{timestamp}.txt"

        output_path = os.path.join(OUTPUT_DIR, output_file)

        # 按强度排序
        signals_sorted = sorted(signals, key=lambda x: (x['strength'], x['risk_reward']), reverse=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            # 标题
            f.write("=" * 100 + "\n")
            f.write(" " * 30 + "低位缩量反转策略 - 每日扫描报告\n")
            f.write("=" * 100 + "\n\n")

            # 基本信息
            f.write(f"扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"符合条件股票数: {len(signals)}只\n")
            if signals:
                avg_strength = sum(s['strength'] for s in signals) / len(signals)
                avg_risk_reward = sum(s['risk_reward'] for s in signals) / len(signals)
                f.write(f"平均信号强度: {avg_strength:.1f}\n")
                f.write(f"平均风险回报比: {avg_risk_reward:.2f}\n")
            f.write("\n")

            # 按强度分组
            strength_groups = {3: [], 2: [], 1: [], 0: []}
            for signal in signals_sorted:
                strength = signal['strength']
                strength_groups[strength].append(signal)

            # 输出各强度级别的信号
            for strength in [3, 2, 1, 0]:
                group = strength_groups[strength]
                if not group:
                    continue

                f.write("-" * 100 + "\n")
                f.write(f"【强度{strength}级信号】（{len(group)}只）\n")
                f.write("-" * 100 + "\n\n")

                for idx, signal in enumerate(group, 1):
                    self._write_signal_detail(f, idx, signal)

        logger.info(f"✓ 报告已保存: {output_path}")
        return output_path

    def _write_signal_detail(self, f, idx: int, signal: Dict):
        """写入单个信号的详细信息"""
        f.write(f"{idx}. {signal['ts_code']} {signal['stock_name']}\n")
        f.write(f"   日期: {signal['date']}\n")
        f.write(f"   当前价: {signal['price']:.2f} | "
                f"止损: {signal['stop_loss']:.2f} ({signal['potential_loss_pct']:+.2f}%) | "
                f"目标: {signal['target']:.2f} ({signal['potential_gain_pct']:+.2f}%)\n")
        f.write(f"   风险回报比: 1:{signal['risk_reward']:.2f}\n")
        f.write(f"\n")

        f.write(f"   市场结构: {signal['structure']} (置信度{signal['structure_confidence']:.2f})\n")
        f.write(f"   {signal['structure_detail']}\n")
        f.write(f"\n")

        f.write(f"   低位确认: {', '.join(signal['low_conditions'])} ({signal['low_condition_count']}项)\n")
        f.write(f"\n")

        f.write(f"   缩量下跌: {signal['supply_dry_days']}天, "
                f"{signal['supply_dry_count']}次SUPPLY_DRY_UP, "
                f"平均量倍数{signal['supply_dry_avg_volume']:.2f}\n")
        f.write(f"   区间最低价: {signal['supply_dry_low']:.2f}\n")
        f.write(f"\n")

        f.write(f"   放量确认: {signal['volume_confirm_type']}, "
                f"今日量倍数{signal['volume_multiple']:.2f}\n")
        f.write(f"   {signal['healthy_up_details']}\n")
        f.write(f"\n")

        f.write(f"   综合描述: {signal['description']}\n")
        f.write(f"\n\n")


def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(description='低位缩量反转策略扫描器')

    # 股票池选项
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--pool', type=str,
                      help='股票池文件路径（如 pool/stock_pool_all.txt）')
    group.add_argument('--code', type=str,
                      help='单只股票代码（如 688256.SH）')

    # 其他选项
    parser.add_argument('--name', type=str, default='',
                       help='股票名称（配合--code使用）')
    parser.add_argument('--use-local-db', action='store_true', default=True,
                       help='使用本地数据库（默认）')
    parser.add_argument('--use-tushare', action='store_true',
                       help='使用Tushare在线数据')
    parser.add_argument('--test', action='store_true',
                       help='测试模式（仅扫描前10只股票）')
    parser.add_argument('--plot', action='store_true',
                       help='生成K线标注图（仅单只股票模式）')
    parser.add_argument('--output', type=str,
                       help='报告输出文件名（可选）')
    parser.add_argument('--verbose', action='store_true',
                       help='详细输出模式')

    args = parser.parse_args()

    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 确定数据源
    use_local_db = not args.use_tushare

    # 初始化扫描器
    scanner = LowVolumeScanner(use_local_db=use_local_db)

    # 扫描
    all_signals = []

    if args.code:
        # 单只股票模式
        logger.info(f"单只股票扫描模式: {args.code} {args.name}")
        signals = scanner.scan_single_stock(args.code, args.name)
        all_signals.extend(signals)

        if signals and args.plot:
            logger.info("生成K线标注图...")
            # TODO: 实现K线标注图生成
            logger.warning("K线标注图功能待实现")

    elif args.pool:
        # 批量扫描模式
        stock_list = scanner.load_stock_pool(args.pool)
        if not stock_list:
            logger.error("股票池为空，退出")
            sys.exit(1)

        all_signals = scanner.scan_batch(stock_list, test_mode=args.test)

    else:
        # 默认使用small池
        default_pool = os.path.join(project_root, 'pool', 'stock_pool_small.txt')
        if os.path.exists(default_pool):
            logger.info(f"使用默认股票池: {default_pool}")
            stock_list = scanner.load_stock_pool(default_pool)
            all_signals = scanner.scan_batch(stock_list, test_mode=args.test)
        else:
            logger.error("未指定--pool或--code参数，且默认池不存在")
            parser.print_help()
            sys.exit(1)

    # 生成报告
    if all_signals:
        report_path = scanner.generate_report(all_signals, args.output)
        logger.info("=" * 80)
        logger.info(f"✅ 扫描完成！发现{len(all_signals)}个信号")
        logger.info(f"📄 报告: {report_path}")
        logger.info("=" * 80)

        # 输出TOP3信号摘要
        logger.info("\nTOP 3 信号摘要:")
        for i, signal in enumerate(sorted(all_signals, key=lambda x: (x['strength'], x['risk_reward']), reverse=True)[:3], 1):
            logger.info(f"{i}. {signal['ts_code']} {signal['stock_name']} - "
                       f"强度{signal['strength']}, 风险回报比{signal['risk_reward']:.2f}, "
                       f"当前价{signal['price']:.2f}")
    else:
        logger.info("=" * 80)
        logger.info("未发现符合条件的信号")
        logger.info("=" * 80)


if __name__ == '__main__':
    main()
