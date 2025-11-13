#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VSA量价分析扫描器

扫描股票池中符合VSA买入条件的股票
支持三种右侧买入信号：
1. TEST_ENTRY - 缩量回调后需求确认
2. BREAKOUT_PULLBACK - 突破-回踩
3. SELLING_CLIMAX - 恐慌抛售后吸筹确认

使用方法:
    python scripts/vsa_scanner.py --pool stock_pool.txt
    python scripts/vsa_scanner.py --code 600519.SH
    python scripts/vsa_scanner.py --pool stock_pool.txt --output vsa_signals.csv
"""

import os
import sys
import argparse
import pandas as pd
from datetime import datetime, timedelta
import logging

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.db_manager import StockDatabase
from strategies.vsa_strategy import VSAStrategy
from analysis.market_structure import MarketStructureAnalyzer
from config.vsa_config import STRATEGY_PARAMS, DATA_PARAMS

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VSAScanner:
    """VSA扫描器"""

    def __init__(self, db_path=None):
        """
        初始化VSA扫描器

        参数:
            db_path: 数据库路径（可选）
        """
        self.db = StockDatabase(db_path)
        self.strategy = VSAStrategy()
        self.structure_analyzer = MarketStructureAnalyzer()
        logger.info("VSA扫描器初始化完成")

    def scan_stock(self, ts_code: str, days: int = 60) -> dict:
        """
        扫描单只股票

        参数:
            ts_code: 股票代码（如：600519.SH）
            days: 分析天数

        返回:
            包含扫描结果的字典
        """
        logger.info(f"开始扫描 {ts_code}")

        try:
            # 获取日线数据
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

            # 获取OHLCV和指标数据
            df = self.db.get_combined_data(ts_code, start_date, end_date)

            if df is None or df.empty:
                logger.warning(f"{ts_code} 无数据")
                return {
                    'ts_code': ts_code,
                    'status': 'NO_DATA',
                    'signals': []
                }

            # 检查是否有VMA数据
            if 'vma20' not in df.columns or df['vma20'].isna().all():
                logger.warning(f"{ts_code} 缺少VMA数据，尝试计算...")
                # 临时计算VMA
                df['vma20'] = df['vol'].rolling(window=20).mean()
                df['volume_multiple'] = df['vol'] / df['vma20']

            if len(df) < STRATEGY_PARAMS['min_data_days']:
                logger.warning(f"{ts_code} 数据不足（需要{STRATEGY_PARAMS['min_data_days']}天）")
                return {
                    'ts_code': ts_code,
                    'status': 'INSUFFICIENT_DATA',
                    'signals': []
                }

            # 首先判断市场结构
            structure, confidence, details = self.structure_analyzer.analyze_structure(df)

            # 扫描入场信号
            signals = self.strategy.scan_entry_signals(df)

            # 获取最新价格和基本信息
            latest = df.iloc[-1]

            result = {
                'ts_code': ts_code,
                'status': 'SUCCESS',
                'latest_price': latest['close'],
                'latest_date': latest['trade_date'],
                'market_structure': structure,
                'structure_confidence': confidence,
                'structure_details': details,
                'signals': signals,
            }

            if signals:
                logger.info(f"{ts_code} 发现 {len(signals)} 个信号")
            else:
                logger.info(f"{ts_code} 无信号")

            return result

        except Exception as e:
            logger.error(f"{ts_code} 扫描失败: {e}")
            return {
                'ts_code': ts_code,
                'status': 'ERROR',
                'error': str(e),
                'signals': []
            }

    def scan_pool(self, pool_file: str, days: int = 60) -> tuple:
        """
        扫描股票池

        参数:
            pool_file: 股票池文件路径（每行一个股票代码，支持#注释）
            days: 分析天数

        返回:
            (DataFrame, dict): 包含所有信号的DataFrame和统计信息字典
        """
        logger.info(f"开始扫描股票池: {pool_file}")

        # 读取股票池
        stocks = self._read_pool(pool_file)
        logger.info(f"股票池包含 {len(stocks)} 只股票")

        # 统计信息
        stats = {
            'total': len(stocks),
            'with_signals': 0,
            'no_signals': 0,
            'no_data': 0,
            'error': 0
        }

        # 扫描所有股票
        all_results = []
        stocks_with_signals = set()

        for i, (code, name) in enumerate(stocks, 1):
            logger.info(f"[{i}/{len(stocks)}] 扫描 {code} {name}")

            result = self.scan_stock(code, days)

            # 统计状态
            status = result.get('status', 'UNKNOWN')
            if status == 'NO_DATA' or status == 'INSUFFICIENT_DATA':
                stats['no_data'] += 1
            elif status == 'ERROR':
                stats['error'] += 1

            # 如果有信号，添加到结果中
            if result.get('signals'):
                stocks_with_signals.add(code)
                for signal in result['signals']:
                    all_results.append({
                        'ts_code': code,
                        'name': name,
                        'latest_price': result.get('latest_price', 0),
                        'latest_date': result.get('latest_date', ''),
                        'market_structure': result.get('market_structure', ''),
                        'structure_confidence': result.get('structure_confidence', 0),
                        **signal
                    })

        # 更新统计信息
        stats['with_signals'] = len(stocks_with_signals)
        stats['no_signals'] = stats['total'] - stats['with_signals'] - stats['no_data'] - stats['error']

        # 转换为DataFrame
        if all_results:
            df_results = pd.DataFrame(all_results)
            logger.info(f"扫描完成，共发现 {len(df_results)} 个信号")
            return df_results, stats
        else:
            logger.info("扫描完成，未发现信号")
            return pd.DataFrame(), stats

    def _read_pool(self, pool_file: str) -> list:
        """
        读取股票池文件

        文件格式：
            每行一个股票代码，可用#添加注释
            示例：
                600519.SH  # 贵州茅台
                000858.SZ  # 五粮液

        参数:
            pool_file: 股票池文件路径

        返回:
            [(ts_code, name), ...] 列表
        """
        stocks = []

        if not os.path.exists(pool_file):
            logger.error(f"股票池文件不存在: {pool_file}")
            return stocks

        with open(pool_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # 跳过空行和注释行
                if not line or line.startswith('#'):
                    continue

                # 解析代码和名称
                parts = line.split('#')
                code = parts[0].strip()

                # 提取名称（如果有）
                if len(parts) > 1:
                    name = parts[1].strip()
                else:
                    name = ''

                stocks.append((code, name))

        return stocks

    def generate_txt_summary(self, df_results: pd.DataFrame, pool_file: str,
                            days: int, total_stocks: int, stats: dict) -> str:
        """
        生成VSA扫描报告TXT文件

        参数:
            df_results: 扫描结果DataFrame
            pool_file: 股票池文件路径
            days: 分析天数
            total_stocks: 总扫描股票数
            stats: 统计信息字典

        返回:
            生成的txt文件路径
        """
        from collections import Counter

        scan_time = datetime.now()
        timestamp = scan_time.strftime('%Y%m%d_%H%M%S')

        # 创建输出目录
        output_dir = "vsa_reports"
        os.makedirs(output_dir, exist_ok=True)

        filename = os.path.join(output_dir, f"vsa_summary_{timestamp}.txt")

        # 准备数据
        if not df_results.empty:
            # 按风险回报比降序排序
            df_sorted = df_results.sort_values('risk_reward', ascending=False, na_position='last')
        else:
            df_sorted = df_results

        lines = []

        # ========================================
        # 1. 报告头部
        # ========================================
        lines.append("=" * 80)
        lines.append(" " * 28 + "VSA量价分析扫描报告")
        lines.append("=" * 80)
        lines.append(f"扫描时间: {scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"股票池: {pool_file}")
        lines.append(f"分析周期: {days}天")
        lines.append(f"扫描股票数: {total_stocks}只")
        lines.append(f"发现信号数: {len(df_results)}个")
        lines.append("")

        if df_results.empty:
            lines.append("=" * 80)
            lines.append(" " * 28 + "未发现符合条件的买入信号")
            lines.append("=" * 80)
            lines.append("")

            # 添加统计信息
            if stats:
                lines.append("【扫描覆盖统计】")
                lines.append(f"  总扫描股票数: {stats.get('total', 0)}只")
                lines.append(f"  有信号股票数: {stats.get('with_signals', 0)}只")
                lines.append(f"  无信号股票数: {stats.get('no_signals', 0)}只")
                lines.append(f"  无数据/数据不足: {stats.get('no_data', 0)}只")
                lines.append(f"  扫描失败: {stats.get('error', 0)}只")
                lines.append("")
        else:
            # ========================================
            # 2. 核心摘要 - 全部信号
            # ========================================
            lines.append("=" * 80)
            lines.append(" " * 28 + "核心摘要 - 全部信号")
            lines.append("=" * 80)

            top5 = df_sorted

            # 表格头部
            lines.append(f"{'排名':<4}  {'代码':<12}  {'名称':<10}  {'信号类型':<18}  "
                        f"{'当前价':<8}  {'目标价':<8}  {'止损价':<8}  {'风险回报比':<10}  {'强度':<4}")
            lines.append("-" * 80)

            for idx, (_, row) in enumerate(top5.iterrows(), 1):
                signal_type_map = {
                    'TEST_ENTRY': 'TEST_ENTRY',
                    'BREAKOUT_PULLBACK': 'BREAKOUT_PB',
                    'SELLING_CLIMAX': 'SELLING_CLIMAX'
                }
                signal_type = signal_type_map.get(row.get('type', ''), row.get('type', 'N/A'))
                strength_stars = '★' * int(row.get('strength', 0))

                lines.append(f"{idx:<4}  {row['ts_code']:<12}  {row.get('name', ''):<10}  "
                           f"{signal_type:<18}  "
                           f"{row.get('latest_price', 0):>8.2f}  "
                           f"{row.get('target', 0):>8.2f}  "
                           f"{row.get('stop_loss', 0):>8.2f}  "
                           f"{row.get('risk_reward', 0):>10.2f}  "
                           f"{strength_stars:<4}")

            lines.append("")

            # ========================================
            # 3. 完整信号列表
            # ========================================
            lines.append("=" * 80)
            lines.append(" " * 20 + "完整信号列表（按风险回报比排序）")
            lines.append("=" * 80)
            lines.append("")

            for idx, (_, row) in enumerate(df_sorted.iterrows(), 1):
                # 信号类型映射
                type_map = {
                    'TEST_ENTRY': 'TEST_ENTRY - 缩量回调后需求确认',
                    'BREAKOUT_PULLBACK': 'BREAKOUT_PULLBACK - 突破回踩确认',
                    'SELLING_CLIMAX': 'SELLING_CLIMAX - 恐慌抛售后吸筹确认'
                }

                # 强度星号
                strength = int(row.get('strength', 0))
                strength_stars = '★' * strength
                strength_text = {3: '极强', 2: '较强', 1: '一般'}.get(strength, '未知')

                lines.append(f"[{idx}] {row.get('name', '')} ({row['ts_code']}) {strength_stars}")
                lines.append("─" * 60)
                lines.append(f"  信号类型: {type_map.get(row.get('type', ''), row.get('type', 'N/A'))}")
                lines.append(f"  市场结构: {row.get('market_structure', 'N/A')} "
                           f"(置信度: {row.get('structure_confidence', 0):.1%})")
                lines.append(f"  信号日期: {row.get('date', 'N/A')}")
                lines.append(f"  当前价格: {row.get('latest_price', 0):.2f}元")

                # 计算止损和目标百分比
                price = row.get('latest_price', 0)
                stop_loss = row.get('stop_loss', 0)
                target = row.get('target', 0)

                if price > 0:
                    stop_pct = ((stop_loss - price) / price) * 100
                    target_pct = ((target - price) / price) * 100
                else:
                    stop_pct = 0
                    target_pct = 0

                lines.append(f"  止损位置: {stop_loss:.2f}元 ({stop_pct:+.1f}%)")
                lines.append(f"  目标位置: {target:.2f}元 ({target_pct:+.1f}%)")

                # 风险回报比详细
                risk = abs(price - stop_loss)
                reward = abs(target - price)
                lines.append(f"  风险回报: {row.get('risk_reward', 0):.2f}:1 "
                           f"(风险{risk:.2f}元，回报{reward:.2f}元)")

                lines.append(f"  信号强度: {strength_stars} ({strength_text})")
                lines.append(f"  信号描述: {row.get('description', 'N/A')}")
                lines.append("─" * 60)
                lines.append("")

            # ========================================
            # 4. 统计分析
            # ========================================
            lines.append("=" * 80)
            lines.append(" " * 32 + "统计分析")
            lines.append("=" * 80)
            lines.append("")

            # 4.1 信号类型分布
            lines.append("【信号类型分布】")
            type_counts = df_results['type'].value_counts()
            type_names = {
                'TEST_ENTRY': 'TEST_ENTRY (缩量回调确认)',
                'BREAKOUT_PULLBACK': 'BREAKOUT_PULLBACK (突破回踩)',
                'SELLING_CLIMAX': 'SELLING_CLIMAX (恐慌后吸筹)'
            }

            for signal_type, count in type_counts.items():
                pct = (count / len(df_results)) * 100
                lines.append(f"  {type_names.get(signal_type, signal_type):<35}  "
                           f"{count:>2}个 ({pct:>5.1f}%)")
            lines.append("")

            # 4.2 信号强度分级
            lines.append("【信号强度分级】")
            strength_groups = df_results.groupby('strength').agg({
                'risk_reward': 'mean',
                'ts_code': 'count'
            }).sort_index(ascending=False)

            strength_labels = {3: '★★★ 极强信号 (强度3)', 2: '★★  较强信号 (强度2)', 1: '★   一般信号 (强度1)'}

            for strength_val, row_data in strength_groups.iterrows():
                count = int(row_data['ts_code'])
                avg_rr = row_data['risk_reward']
                pct = (count / len(df_results)) * 100
                label = strength_labels.get(int(strength_val), f'强度{strength_val}')
                lines.append(f"  {label:<30}  {count:>2}个 ({pct:>5.1f}%) - 平均回报比: {avg_rr:.2f}")
            lines.append("")

            # 4.3 市场结构分析
            lines.append("【市场结构分析】")
            structure_counts = df_results['market_structure'].value_counts()

            for structure, count in structure_counts.items():
                structure_label = {
                    'MARK_UP': 'MARK_UP (上涨区)',
                    'MARK_DOWN': 'MARK_DOWN (下跌区)',
                    'ACCUMULATION': 'ACCUMULATION (吸筹区)',
                    'DISTRIBUTION': 'DISTRIBUTION (派发区)'
                }.get(structure, structure)
                lines.append(f"  {structure_label} 信号数: {count}个")

            avg_confidence = df_results['structure_confidence'].mean()
            max_confidence = df_results['structure_confidence'].max()
            min_confidence = df_results['structure_confidence'].min()

            lines.append(f"  平均结构置信度: {avg_confidence:.1%}")

            max_conf_row = df_results.loc[df_results['structure_confidence'].idxmax()]
            min_conf_row = df_results.loc[df_results['structure_confidence'].idxmin()]

            lines.append(f"  最高置信度: {max_confidence:.1%} "
                        f"({max_conf_row['ts_code']} {max_conf_row.get('name', '')})")
            lines.append(f"  最低置信度: {min_confidence:.1%} "
                        f"({min_conf_row['ts_code']} {min_conf_row.get('name', '')})")
            lines.append("")

            # 4.4 风险回报概览
            lines.append("【风险回报概览】")
            avg_rr = df_results['risk_reward'].mean()
            max_rr = df_results['risk_reward'].max()
            min_rr = df_results['risk_reward'].min()

            max_rr_row = df_results.loc[df_results['risk_reward'].idxmax()]
            min_rr_row = df_results.loc[df_results['risk_reward'].idxmin()]

            lines.append(f"  平均风险回报比: {avg_rr:.2f}:1")
            lines.append(f"  最佳回报比: {max_rr:.2f}:1 "
                        f"({max_rr_row['ts_code']} {max_rr_row.get('name', '')})")
            lines.append(f"  最差回报比: {min_rr:.2f}:1 "
                        f"({min_rr_row['ts_code']} {min_rr_row.get('name', '')})")

            # 计算平均潜在收益和止损风险
            avg_target_pct = df_results.apply(
                lambda x: ((x['target'] - x['latest_price']) / x['latest_price'] * 100)
                if x['latest_price'] > 0 else 0, axis=1
            ).mean()

            avg_stop_pct = df_results.apply(
                lambda x: ((x['stop_loss'] - x['latest_price']) / x['latest_price'] * 100)
                if x['latest_price'] > 0 else 0, axis=1
            ).mean()

            lines.append(f"  平均潜在收益: {avg_target_pct:+.1f}%")
            lines.append(f"  平均止损风险: {avg_stop_pct:+.1f}%")
            lines.append("")

            # 4.5 扫描覆盖统计
            lines.append("【扫描覆盖统计】")
            if stats:
                lines.append(f"  总扫描股票数: {stats.get('total', 0)}只")
                lines.append(f"  有信号股票数: {stats.get('with_signals', 0)}只")
                lines.append(f"  无信号股票数: {stats.get('no_signals', 0)}只")

                trigger_rate = (stats.get('with_signals', 0) / stats.get('total', 1)) * 100
                lines.append(f"  信号触发率: {trigger_rate:.1f}%")
                lines.append(f"  无数据/数据不足: {stats.get('no_data', 0)}只")
                lines.append(f"  扫描失败: {stats.get('error', 0)}只")
            lines.append("")

            # ========================================
            # 5. 风险提示
            # ========================================
            lines.append("=" * 80)
            lines.append(" " * 32 + "风险提示")
            lines.append("=" * 80)
            lines.append("1. 本报告基于VSA量价分析方法，仅供参考，不构成投资建议")
            lines.append("2. 所有信号需结合实时行情、基本面、市场环境综合判断")
            lines.append("3. 建议严格执行止损策略，控制单笔风险在总资金的2-3%以内")
            lines.append("4. 高风险回报比信号未必代表高胜率，注意仓位管理")
            lines.append("5. 市场结构置信度低于75%的信号需谨慎对待")
            lines.append("6. 建议在信号出现后次日开盘前再次确认市场环境")
            lines.append("")

        # ========================================
        # 6. 报告尾部
        # ========================================
        lines.append("=" * 80)
        lines.append(f"报告生成时间: {scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("VSA Scanner Version: 1.0")
        lines.append("=" * 80)

        # 写入文件
        content = "\n".join(lines)

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"TXT总结报告已生成: {filename}")
        return filename

    def close(self):
        """关闭数据库连接"""
        if self.db:
            self.db.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='VSA量价分析扫描器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  扫描股票池:
    python scripts/vsa_scanner.py --pool my_stocks.txt

  扫描单只股票:
    python scripts/vsa_scanner.py --code 600519.SH

  保存结果到CSV:
    python scripts/vsa_scanner.py --pool my_stocks.txt --output signals.csv

  指定分析天数:
    python scripts/vsa_scanner.py --pool my_stocks.txt --days 90
        """
    )

    parser.add_argument('--pool', help='股票池文件路径')
    parser.add_argument('--code', help='单只股票代码（如：600519.SH）')
    parser.add_argument('--days', type=int, default=60, help='分析天数（默认60天）')
    parser.add_argument('--output', help='输出CSV文件路径')
    parser.add_argument('--db', help='数据库路径（可选）')

    args = parser.parse_args()

    # 检查参数
    if not args.pool and not args.code:
        parser.error("必须指定 --pool 或 --code")

    # 初始化扫描器
    scanner = VSAScanner(db_path=args.db)

    try:
        if args.code:
            # 扫描单只股票
            result = scanner.scan_stock(args.code, args.days)

            print("\n" + "=" * 80)
            print(f"股票代码: {result['ts_code']}")
            print(f"扫描状态: {result['status']}")

            if result['status'] == 'SUCCESS':
                print(f"最新价格: {result.get('latest_price', 'N/A')}")
                print(f"最新日期: {result.get('latest_date', 'N/A')}")
                print(f"市场结构: {result.get('market_structure', 'N/A')} "
                      f"(置信度: {result.get('structure_confidence', 0):.2%})")
                print(f"结构描述: {result.get('structure_details', 'N/A')}")

                signals = result.get('signals', [])
                if signals:
                    print(f"\n发现 {len(signals)} 个入场信号:")
                    print("-" * 80)
                    for i, signal in enumerate(signals, 1):
                        print(f"\n信号 #{i}")
                        print(f"  类型: {signal['type']}")
                        print(f"  日期: {signal['date']}")
                        print(f"  价格: {signal['price']:.2f}")
                        print(f"  强度: {signal['strength']}")
                        print(f"  描述: {signal['description']}")
                        print(f"  止损: {signal['stop_loss']:.2f}")
                        print(f"  目标: {signal['target']:.2f}")
                        print(f"  风险回报比: {signal.get('risk_reward', 'N/A')}")
                else:
                    print("\n未发现入场信号")
            elif result['status'] == 'ERROR':
                print(f"错误: {result.get('error', 'Unknown error')}")

            print("=" * 80)

        else:
            # 扫描股票池
            df_results, stats = scanner.scan_pool(args.pool, args.days)

            if not df_results.empty:
                print(f"\n发现 {len(df_results)} 个入场信号:\n")

                # 格式化输出
                display_cols = [
                    'ts_code', 'name', 'latest_price', 'type',
                    'price', 'strength', 'description',
                    'stop_loss', 'target', 'risk_reward'
                ]
                available_cols = [col for col in display_cols if col in df_results.columns]

                print(df_results[available_cols].to_string(index=False))

                # 保存到CSV
                if args.output:
                    df_results.to_csv(args.output, index=False, encoding='utf-8-sig')
                    print(f"\n结果已保存到: {args.output}")
            else:
                print("\n未发现符合条件的买入信号")

            # 自动生成TXT总结报告
            print("\n正在生成详细总结报告...")
            txt_file = scanner.generate_txt_summary(
                df_results=df_results,
                pool_file=args.pool,
                days=args.days,
                total_stocks=stats['total'],
                stats=stats
            )
            print(f"详细总结报告已生成: {txt_file}")

    finally:
        scanner.close()


if __name__ == '__main__':
    main()
