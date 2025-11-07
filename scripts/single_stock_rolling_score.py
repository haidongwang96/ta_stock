#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单股票滚动窗口打分系统
基于 daily_stock_scoring.py 的打分逻辑，对单个股票进行历史滚动窗口打分

功能：
1. 生成趋势图表：可视化得分历史变化
2. 寻找买卖时机：识别得分突破信号
3. 回测验证：验证打分系统的历史表现
4. 监控单个股票：持续追踪关注股票的技术面变化

重要说明：
- 得分与股价对齐方式：第N天的得分对应第N+1天的涨跌幅
- 这样能够评估打分系统对未来走势的预判能力
- 例如：2024-01-15的得分 → 预测 2024-01-16的涨跌

数据源选项：
- 默认使用在线Tushare（需要token.txt文件）
- 可选本地数据库：添加 --use-local-db 参数（需要配置database/query_helper.py）

使用示例：
1. 使用在线Tushare（默认）：
   python single_stock_rolling_score.py --code 000001.SZ --name 平安银行

2. 使用本地数据库（推荐，速度更快）：
   python single_stock_rolling_score.py --code 000001.SZ --name 平安银行 --use-local-db

3. 自定义窗口参数：
   python single_stock_rolling_score.py --code 000001.SZ --use-local-db --num-windows 60 --indicator-window 120

输出：
1. CSV文件：每日得分详细数据
2. 文本报告：趋势分析、买卖建议
3. 可视化图表：多维度图表展示
"""

import os
import sys
import logging
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# ==================== 路径配置 ====================
# 将项目根目录添加到 Python 路径，以便导入 database 模块
# 这样无论从哪个目录运行脚本都能正常工作
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入打分分析器
from daily_stock_scoring import StockScoringAnalyzer, get_score_level

# 导入本地数据库查询模块
try:
    from database.query_helper import StockDataQuery
    LOCAL_DB_AVAILABLE = True
except ImportError:
    LOCAL_DB_AVAILABLE = False

# ==================== 全局配置 ====================

# 输出目录
OUTPUT_DIR = 'rolling_scores_results'

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 创建输出目录
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    logger.info(f"创建输出目录: {OUTPUT_DIR}")

# 配置matplotlib支持中文
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


# ==================== RollingScoreAnalyzer 类 ====================

class RollingScoreAnalyzer:
    """
    单股票滚动窗口打分分析器

    对单个股票进行历史滚动窗口打分，生成得分时间序列
    """

    def __init__(self, stock_code, stock_name=None, use_local_db=False):
        """
        初始化分析器

        Args:
            stock_code: 股票代码（如 '000001.SZ'）
            stock_name: 股票名称（如果为None会自动查询）
            use_local_db: 是否使用本地数据库
        """
        self.stock_code = stock_code
        self.stock_name = stock_name or stock_code

        # 检查本地数据库可用性
        if use_local_db and not LOCAL_DB_AVAILABLE:
            logger.warning("⚠️  本地数据库模块不可用！自动回退到在线Tushare")
            logger.warning("   请确保已正确配置 database/query_helper.py")
            use_local_db = False

        self.use_local_db = use_local_db

        # 创建基础分析器
        self.analyzer = StockScoringAnalyzer(use_local_db=use_local_db)

        # 初始化打分数据仓库
        try:
            from database.score_repository import ScoreRepository
            self.score_repo = ScoreRepository()
            logger.debug("✓ 打分数据仓库初始化成功")
        except Exception as e:
            logger.warning(f"⚠️  打分数据仓库初始化失败: {e}")
            self.score_repo = None

        logger.info(f"初始化滚动窗口分析器: {self.stock_code} ({self.stock_name})")

        # 显示实际使用的数据源
        if self.analyzer.use_local_db:
            logger.info(f"✓ 数据源: 本地数据库")
        else:
            logger.info(f"✓ 数据源: 在线Tushare")

    def calculate_rolling_scores(self, end_date=None, num_windows=30, indicator_window=60,
                                force_recalculate=False):
        """
        计算滚动窗口得分

        Args:
            end_date: 结束日期（YYYYMMDD格式），默认为今天
            num_windows: 要计算的窗口数量（默认30个交易日）
            indicator_window: 每个窗口用于计算技术指标的历史数据天数（默认60天）
            force_recalculate: 是否强制重新计算（默认False，优先读取数据库）

        Returns:
            DataFrame包含所有窗口的得分数据
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')

        logger.info("=" * 80)
        logger.info(f"开始滚动窗口打分分析")
        logger.info(f"股票代码: {self.stock_code} ({self.stock_name})")
        logger.info(f"结束日期: {end_date}")
        logger.info(f"窗口数量: {num_windows} 个交易日")
        logger.info(f"指标计算窗口: {indicator_window} 天")
        logger.info("=" * 80)

        # 尝试从数据库读取（如果未强制重新计算且仓库可用）
        if not force_recalculate and self.score_repo:
            logger.info("\n检查数据库缓存...")
            try:
                df_cached = self.score_repo.load_scores(self.stock_code)

                if df_cached is not None and not df_cached.empty:
                    # 检查数据完整性
                    cached_count = len(df_cached)
                    cached_date_range = (df_cached['date'].min(), df_cached['date'].max())

                    logger.info(f"✓ 从数据库加载打分数据: {cached_count} 条记录")
                    logger.info(f"  日期范围: {cached_date_range[0]} 至 {cached_date_range[1]}")

                    # 如果缓存数据足够（>=请求的窗口数），直接返回
                    if cached_count >= num_windows:
                        logger.info(f"✓ 数据完整，跳过重复计算")

                        # 返回最新的 num_windows 条记录
                        df_results = df_cached.head(num_windows).copy()
                        return df_results
                    else:
                        logger.info(f"⚠️  缓存数据不足 ({cached_count} < {num_windows})，重新计算")
                else:
                    logger.info("✓ 数据库中无打分数据，开始计算...")
            except Exception as e:
                logger.warning(f"⚠️  读取数据库失败: {e}，继续计算...")
        elif force_recalculate:
            logger.info("⚠️  强制重新计算模式")
        else:
            logger.info("✓ 数据库仓库不可用，直接计算")

        # 计算需要获取的总数据量
        # 需要 num_windows 个交易日的得分，每个得分需要 indicator_window 天的数据
        # 考虑到非交易日，获取更多天数以确保有足够的交易日数据
        total_days_needed = (num_windows + indicator_window) * 2  # 乘以2确保足够
        start_date = (datetime.strptime(end_date, '%Y%m%d') - timedelta(days=total_days_needed)).strftime('%Y%m%d')

        logger.info(f"获取数据范围: {start_date} 至 {end_date} (约{total_days_needed}天)")

        # 获取完整的历史数据
        df_full = self.analyzer.fetch_data(self.stock_code, start_date, end_date)

        if df_full is None or df_full.empty:
            logger.error(f"无法获取股票数据: {self.stock_code}")
            return None

        logger.info(f"✓ 成功获取 {len(df_full)} 个交易日的数据")

        # 确保有足够的数据
        if len(df_full) < indicator_window + num_windows:
            logger.warning(f"数据不足：需要至少 {indicator_window + num_windows} 个交易日，"
                         f"实际只有 {len(df_full)} 个交易日")
            # 调整num_windows
            num_windows = max(1, len(df_full) - indicator_window)
            logger.info(f"自动调整窗口数量为: {num_windows}")

        # 存储所有窗口的得分结果
        rolling_results = []

        logger.info(f"\n开始计算 {num_windows} 个滚动窗口的得分...")

        # 滚动窗口计算
        for i in range(num_windows):
            # 计算窗口的起止位置
            # 从最新的数据开始往前滚动
            end_idx = len(df_full) - i
            start_idx = max(0, end_idx - indicator_window)

            # 提取窗口数据
            window_data = df_full.iloc[start_idx:end_idx].copy()

            if len(window_data) < 30:  # 至少需要30天数据才能计算有效指标
                logger.warning(f"窗口 {i+1}: 数据不足 ({len(window_data)}天)，跳过")
                continue

            # 计算技术指标
            window_data = self.analyzer.calculate_trend_indicators(window_data)
            window_data = self.analyzer.calculate_momentum_indicators(window_data)
            window_data = self.analyzer.calculate_volatility_indicators(window_data)
            window_data = self.analyzer.calculate_volume_indicators(window_data)
            window_data = self.analyzer.calculate_support_resistance(window_data)
            window_data = self.analyzer.identify_candle_patterns(window_data)
            window_data = self.analyzer.identify_divergence(window_data)

            # 计算得分
            window_data = self.analyzer.calculate_detailed_scores(window_data)

            # 获取窗口最后一天（最新一天）的得分
            last_row = window_data.iloc[-1]
            current_date = last_row['trade_date']
            current_close = last_row['Close']

            # 计算未来一天的涨跌幅（预判对齐）
            # end_idx 指向的是下一天的数据（如果存在）
            if end_idx < len(df_full):
                # 有未来数据：用下一天相对于今天的涨跌幅
                next_close = df_full.iloc[end_idx]['Close']
                change_pct = ((next_close - current_close) / current_close) * 100
                next_date = df_full.iloc[end_idx]['trade_date']
            else:
                # 最新一天没有未来数据
                change_pct = None
                next_date = None

            # 构建结果记录
            result = {
                'date': current_date,  # 得分对应的日期（第n天）
                'close': current_close,  # 第n天收盘价
                'next_date': next_date,  # 预测的目标日期（第n+1天）
                'change_pct': change_pct,  # 第n+1天相对于第n天的涨跌幅
                'total_score': last_row['Total_Score'],
                'trend_score': last_row['Trend_Score'],
                'momentum_score': last_row['Momentum_Score'],
                'volatility_score': last_row['Volatility_Score'],
                'volume_score': last_row['Volume_Score'],
                'pattern_score': last_row['Pattern_Score'],
                'score_details': last_row['Score_Details'],
                'score_level': get_score_level(last_row['Total_Score']),
            }

            # 添加关键指标
            for col in ['RSI', 'MFI', 'K', 'D', 'J', 'CCI', 'ATR', 'Volume_Ratio']:
                if col in window_data.columns and pd.notna(last_row.get(col)):
                    result[col.lower()] = last_row[col]
                else:
                    result[col.lower()] = None

            rolling_results.append(result)

            # 进度显示
            if (i + 1) % 10 == 0 or i == 0 or i == num_windows - 1:
                logger.info(f"  已完成 {i+1}/{num_windows} 个窗口 "
                          f"({last_row['trade_date']}: 总分{result['total_score']:+.0f})")

        # 转换为DataFrame
        df_results = pd.DataFrame(rolling_results)

        if df_results.empty:
            logger.error("所有窗口都未能成功计算得分")
            return None

        # 按日期降序排序（最新的在前）
        df_results = df_results.sort_values('date', ascending=False).reset_index(drop=True)

        logger.info(f"\n✓ 滚动窗口打分完成！")
        logger.info(f"  成功计算: {len(df_results)} 个窗口")
        logger.info(f"  日期范围: {df_results['date'].min()} 至 {df_results['date'].max()}")
        logger.info(f"  得分范围: {df_results['total_score'].min():+.0f} 至 {df_results['total_score'].max():+.0f}")
        logger.info(f"  平均得分: {df_results['total_score'].mean():+.2f}")

        # 保存到数据库
        if self.score_repo:
            try:
                logger.info(f"\n保存打分数据到数据库...")
                self.score_repo.save_scores(self.stock_code, df_results)
            except Exception as e:
                logger.warning(f"⚠️  保存到数据库失败: {e}")

        return df_results

    def identify_signals(self, df_results):
        """
        识别买卖信号

        Args:
            df_results: 滚动窗口得分DataFrame（按日期降序）

        Returns:
            包含信号的DataFrame
        """
        if df_results is None or df_results.empty:
            return None

        # 反向排序以便于计算变化（从旧到新）
        df = df_results.sort_values('date', ascending=True).copy()

        signals = []

        for i in range(len(df)):
            signal_list = []

            if i > 0:
                # 当前和前一天的得分
                curr_score = df.iloc[i]['total_score']
                prev_score = df.iloc[i-1]['total_score']
                score_change = curr_score - prev_score

                # 信号1：得分从负转正（金叉）
                if prev_score <= 0 and curr_score > 0:
                    signal_list.append('⬆️得分转正')

                # 信号2：得分从正转负（死叉）
                if prev_score >= 0 and curr_score < 0:
                    signal_list.append('⬇️得分转负')

                # 信号3：突破看多区间（>5）
                if prev_score <= 5 and curr_score > 5:
                    signal_list.append('⬆️突破看多区间')

                # 信号4：跌破看空区间（<-5）
                if prev_score >= -5 and curr_score < -5:
                    signal_list.append('⬇️跌破看空区间')

                # 信号5：得分大幅上升（+5分以上）
                if score_change >= 5:
                    signal_list.append(f'⬆️得分大涨(+{score_change:.0f})')

                # 信号6：得分大幅下降（-5分以上）
                if score_change <= -5:
                    signal_list.append(f'⬇️得分大跌({score_change:.0f})')

                # 信号7：连续上升（检查前3天）
                if i >= 2:
                    if (df.iloc[i]['total_score'] > df.iloc[i-1]['total_score'] and
                        df.iloc[i-1]['total_score'] > df.iloc[i-2]['total_score']):
                        signal_list.append('📈连续上升')

                # 信号8：连续下降（检查前3天）
                if i >= 2:
                    if (df.iloc[i]['total_score'] < df.iloc[i-1]['total_score'] and
                        df.iloc[i-1]['total_score'] < df.iloc[i-2]['total_score']):
                        signal_list.append('📉连续下降')

            signals.append('; '.join(signal_list) if signal_list else '-')

        df['signals'] = signals

        # 恢复降序
        df = df.sort_values('date', ascending=False).reset_index(drop=True)

        return df


# ==================== 输出功能 ====================

def save_csv(df, stock_code, output_dir=OUTPUT_DIR):
    """
    保存CSV文件

    Args:
        df: 滚动窗口得分DataFrame
        stock_code: 股票代码
        output_dir: 输出目录

    Returns:
        CSV文件路径
    """
    if df is None or df.empty:
        logger.error("没有数据可保存")
        return None

    filename = f"{stock_code.replace('.', '_')}_rolling_scores.csv"
    filepath = os.path.join(output_dir, filename)

    # 选择要保存的列
    columns_to_save = [
        'date', 'close', 'next_date', 'change_pct',
        'total_score', 'trend_score', 'momentum_score',
        'volatility_score', 'volume_score', 'pattern_score',
        'score_level', 'signals', 'score_details',
        'rsi', 'mfi', 'k', 'd', 'j', 'cci', 'atr', 'volume_ratio'
    ]

    # 只保存存在的列
    columns_to_save = [col for col in columns_to_save if col in df.columns]

    df_save = df[columns_to_save].copy()

    # 重命名列为中文（可选）
    rename_map = {
        'date': '得分日期',
        'close': '当日收盘价',
        'next_date': '预测日期',
        'change_pct': '次日涨跌幅%',
        'total_score': '总分',
        'trend_score': '趋势分',
        'momentum_score': '动量分',
        'volatility_score': '波动分',
        'volume_score': '成交量分',
        'pattern_score': '形态分',
        'score_level': '得分等级',
        'signals': '信号',
        'score_details': '得分详情',
        'rsi': 'RSI',
        'mfi': 'MFI',
        'k': 'K值',
        'd': 'D值',
        'j': 'J值',
        'cci': 'CCI',
        'atr': 'ATR',
        'volume_ratio': '量比'
    }

    df_save.rename(columns=rename_map, inplace=True)

    # 保存
    df_save.to_csv(filepath, index=False, encoding='utf-8-sig', float_format='%.2f')

    logger.info(f"✓ CSV文件已保存: {filepath}")
    return filepath


def generate_text_report(df, stock_code, stock_name, output_dir=OUTPUT_DIR):
    """
    生成文本报告

    Args:
        df: 滚动窗口得分DataFrame
        stock_code: 股票代码
        stock_name: 股票名称
        output_dir: 输出目录

    Returns:
        报告文件路径
    """
    if df is None or df.empty:
        logger.error("没有数据可生成报告")
        return None

    filename = f"{stock_code.replace('.', '_')}_rolling_report.txt"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        # 标题
        f.write("=" * 100 + "\n")
        f.write(f"单股票滚动窗口打分报告\n")
        f.write("=" * 100 + "\n\n")

        # 基本信息
        f.write(f"股票代码: {stock_code}\n")
        f.write(f"股票名称: {stock_name}\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"分析周期: {df['date'].min()} 至 {df['date'].max()}\n")
        f.write(f"分析天数: {len(df)} 个交易日\n\n")

        # 重要说明
        f.write("-" * 100 + "\n")
        f.write("【重要说明】\n")
        f.write("-" * 100 + "\n")
        f.write("本报告采用预判性对齐方式：\n")
        f.write("- 第N天的得分 对应 第N+1天的涨跌幅\n")
        f.write("- 目的：评估打分系统对未来走势的预判能力\n")
        f.write("- 例如：2024-01-15的得分用于预测2024-01-16的涨跌\n")
        f.write("- 因此最新一天的得分没有次日涨跌幅数据（显示为N/A）\n\n")

        # 得分统计
        f.write("-" * 100 + "\n")
        f.write("【得分统计概览】\n")
        f.write("-" * 100 + "\n")
        f.write(f"平均总分: {df['total_score'].mean():+.2f}\n")
        f.write(f"最高总分: {df['total_score'].max():+.0f} (日期: {df[df['total_score'] == df['total_score'].max()]['date'].values[0]})\n")
        f.write(f"最低总分: {df['total_score'].min():+.0f} (日期: {df[df['total_score'] == df['total_score'].min()]['date'].values[0]})\n")
        f.write(f"标准差: {df['total_score'].std():.2f}\n\n")

        # 分项得分统计
        f.write("分项得分平均值:\n")
        f.write(f"  趋势类: {df['trend_score'].mean():+.2f}\n")
        f.write(f"  动量类: {df['momentum_score'].mean():+.2f}\n")
        f.write(f"  波动类: {df['volatility_score'].mean():+.2f}\n")
        f.write(f"  成交量类: {df['volume_score'].mean():+.2f}\n")
        f.write(f"  形态类: {df['pattern_score'].mean():+.2f}\n\n")

        # 价格统计
        f.write("-" * 100 + "\n")
        f.write("【价格统计】\n")
        f.write("-" * 100 + "\n")
        latest_price = df.iloc[0]['close']
        earliest_price = df.iloc[-1]['close']
        price_change = ((latest_price - earliest_price) / earliest_price) * 100

        f.write(f"当前价格: {latest_price:.2f} 元\n")
        f.write(f"期初价格: {earliest_price:.2f} 元\n")
        f.write(f"区间涨跌: {price_change:+.2f}%\n")
        f.write(f"最高价: {df['close'].max():.2f} 元\n")
        f.write(f"最低价: {df['close'].min():.2f} 元\n\n")

        # 趋势分析
        f.write("-" * 100 + "\n")
        f.write("【得分趋势分析】\n")
        f.write("-" * 100 + "\n")

        # 计算近期趋势（最近5天 vs 之前5天）
        if len(df) >= 10:
            recent_avg = df.iloc[:5]['total_score'].mean()
            previous_avg = df.iloc[5:10]['total_score'].mean()
            trend_change = recent_avg - previous_avg

            if trend_change > 2:
                trend_desc = "上升趋势 ⬆️"
            elif trend_change < -2:
                trend_desc = "下降趋势 ⬇️"
            else:
                trend_desc = "横盘震荡 ➡️"

            f.write(f"近期趋势: {trend_desc}\n")
            f.write(f"  最近5日平均分: {recent_avg:+.2f}\n")
            f.write(f"  之前5日平均分: {previous_avg:+.2f}\n")
            f.write(f"  趋势变化: {trend_change:+.2f}\n\n")

        # 关键信号
        f.write("-" * 100 + "\n")
        f.write("【关键信号识别】\n")
        f.write("-" * 100 + "\n")

        # 筛选有信号的记录
        df_with_signals = df[df['signals'] != '-'].copy()

        if not df_with_signals.empty:
            f.write(f"共识别 {len(df_with_signals)} 个交易日出现关键信号:\n\n")

            for idx, row in df_with_signals.iterrows():
                f.write(f"{row['date']}: {row['signals']}\n")
                change_str = f"{row['change_pct']:+.2f}%" if pd.notna(row['change_pct']) else "N/A"
                f.write(f"  总分: {row['total_score']:+.0f} | 收盘价: {row['close']:.2f} | "
                       f"次日涨跌幅: {change_str}\n")
                f.write(f"  得分详情: {row['score_details'][:100]}...\n\n")
        else:
            f.write("未识别到关键信号\n\n")

        # 买卖建议
        f.write("-" * 100 + "\n")
        f.write("【买卖建议】\n")
        f.write("-" * 100 + "\n")

        latest_score = df.iloc[0]['total_score']
        latest_level = df.iloc[0]['score_level']

        f.write(f"当前得分: {latest_score:+.0f} ({latest_level})\n\n")

        if latest_score >= 8:
            suggestion = "强烈建议关注 ⭐⭐⭐ - 技术面非常强势，可考虑买入或持有"
        elif latest_score >= 5:
            suggestion = "建议关注 ⭐⭐ - 技术面较强，可考虑逢低买入"
        elif latest_score >= 2:
            suggestion = "谨慎关注 ⭐ - 技术面偏多，观望为主"
        elif latest_score >= -1:
            suggestion = "中性观望 - 技术面中性，等待明确信号"
        elif latest_score >= -4:
            suggestion = "谨慎 ⚠️ - 技术面偏弱，注意风险"
        elif latest_score >= -7:
            suggestion = "建议减仓 ⚠️⚠️ - 技术面较弱，考虑减仓或止损"
        else:
            suggestion = "强烈建议减仓 ⚠️⚠️⚠️ - 技术面非常弱，建议及时止损"

        f.write(f"{suggestion}\n\n")

        # 最近10天得分明细
        f.write("-" * 100 + "\n")
        f.write("【最近10个交易日得分明细】\n")
        f.write("-" * 100 + "\n")
        f.write(f"{'日期':<12}{'收盘价':<10}{'次日涨跌':<10}{'总分':<8}{'趋势':<6}{'动量':<6}"
               f"{'波动':<6}{'成交量':<8}{'形态':<6}{'等级':<12}{'信号'}\n")
        f.write("-" * 100 + "\n")

        for idx, row in df.head(10).iterrows():
            date_str = str(row['date'])[:10]  # 只取日期部分 YYYY-MM-DD
            change_str = f"{row['change_pct']:>+7.2f}%" if pd.notna(row['change_pct']) else "    N/A   "
            f.write(f"{date_str:<12}{row['close']:>8.2f}  {change_str}  "
                   f"{row['total_score']:>+5.0f}  {row['trend_score']:>+4.0f}  {row['momentum_score']:>+4.0f}  "
                   f"{row['volatility_score']:>+4.0f}  {row['volume_score']:>+6.0f}  {row['pattern_score']:>+4.0f}  "
                   f"{row['score_level']:<12}{row['signals']}\n")

        f.write("\n" + "=" * 100 + "\n")
        f.write("报告结束\n")
        f.write("=" * 100 + "\n")

    logger.info(f"✓ 文本报告已保存: {filepath}")
    return filepath


def generate_charts(df, stock_code, stock_name, output_dir=OUTPUT_DIR):
    """
    生成可视化图表

    Args:
        df: 滚动窗口得分DataFrame
        stock_code: 股票代码
        stock_name: 股票名称
        output_dir: 输出目录

    Returns:
        图表文件路径
    """
    if df is None or df.empty:
        logger.error("没有数据可生成图表")
        return None

    filename = f"{stock_code.replace('.', '_')}_rolling_charts.png"
    filepath = os.path.join(output_dir, filename)

    # 准备数据（按日期升序）
    df_plot = df.sort_values('date', ascending=True).copy()

    # 处理日期格式（兼容YYYYMMDD和datetime对象）
    if df_plot['date'].dtype == 'object':
        # 字符串格式，尝试解析
        try:
            df_plot['date'] = pd.to_datetime(df_plot['date'], format='%Y%m%d')
        except:
            df_plot['date'] = pd.to_datetime(df_plot['date'])
    elif not pd.api.types.is_datetime64_any_dtype(df_plot['date']):
        # 其他格式，直接转换
        df_plot['date'] = pd.to_datetime(df_plot['date'])

    # 计算累计涨跌幅（相对于第一天）
    first_close = df_plot['close'].iloc[0]
    df_plot['cumulative_return'] = ((df_plot['close'] - first_close) / first_close) * 100

    # 计算当日涨跌幅（相对于前一天）
    df_plot['daily_return'] = df_plot['close'].pct_change() * 100

    # 创建图表（2行2列）
    fig, axes = plt.subplots(2, 2, figsize=(20, 12))
    fig.suptitle(f'{stock_name} ({stock_code}) - 滚动窗口打分分析',
                 fontsize=16, fontweight='bold', y=0.995)

    # ========== 子图1: 总分趋势 + 当日涨跌幅（双y轴）==========
    ax1 = axes[0, 0]
    ax1_twin = ax1.twinx()

    # 创建均匀分布的x轴索引（去掉非交易日）
    x_indices = np.arange(len(df_plot))

    # 绘制总分
    line1 = ax1.plot(x_indices, df_plot['total_score'],
                     color='#2E86AB', linewidth=2, marker='o', markersize=4,
                     label='总分')
    ax1.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.5)
    ax1.axhline(y=5, color='green', linestyle=':', linewidth=1, alpha=0.5, label='看多线(+5)')
    ax1.axhline(y=-5, color='red', linestyle=':', linewidth=1, alpha=0.5, label='看空线(-5)')
    ax1.fill_between(x_indices, 0, df_plot['total_score'],
                     where=(df_plot['total_score'] >= 0), alpha=0.2, color='green', label='正分区域')
    ax1.fill_between(x_indices, 0, df_plot['total_score'],
                     where=(df_plot['total_score'] < 0), alpha=0.2, color='red', label='负分区域')

    # 绘制当日涨跌幅（柱状图）- 涨红跌绿
    bar_colors = ['#FF3333' if x >= 0 else '#00CC00' for x in df_plot['daily_return']]
    line2 = ax1_twin.bar(x_indices, df_plot['daily_return'],
                          color=bar_colors, alpha=0.6, width=0.8,
                          label='当日涨跌幅')

    # 在柱子上标注涨跌幅数值
    for i, (idx, val) in enumerate(zip(x_indices, df_plot['daily_return'])):
        if pd.notna(val):  # 只标注有效值
            # 根据正负值决定标注位置
            if val >= 0:
                va = 'bottom'
                y_pos = val
            else:
                va = 'top'
                y_pos = val
            ax1_twin.text(idx, y_pos, f'{val:.1f}%',
                         ha='center', va=va, fontsize=7,
                         color='black', rotation=0)

    # 添加0%基准线
    ax1_twin.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.5)

    # 对齐两个y轴的0点，使刻度一致
    # 计算两个数据的最大绝对值
    score_max = max(abs(df_plot['total_score'].min()), abs(df_plot['total_score'].max()))
    return_max = max(abs(df_plot['daily_return'].min()), abs(df_plot['daily_return'].max()))
    # 使用较大的范围，确保所有数据都能显示（增加更多边距以容纳标注）
    y_max = max(score_max, return_max) * 1.3  # 增加30%的边距
    # 设置两个y轴使用相同的范围
    ax1.set_ylim(-y_max, y_max)
    ax1_twin.set_ylim(-y_max, y_max)

    # 在总分点位下方10%处标注得分
    y_range = y_max * 2  # 总的y轴范围
    offset = y_range * 0.10  # 10%的偏移量
    for idx, score in zip(x_indices, df_plot['total_score']):
        # 标注位置在得分点下方10%
        y_pos = score - offset
        ax1.text(idx, y_pos, f'{score:+.0f}',
                ha='center', va='top', fontsize=7,
                color='#2E86AB', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#2E86AB', alpha=0.7))

    # 设置x轴刻度标签为日期（每隔几个显示）
    step = max(1, len(df_plot) // 15)  # 显示约15个日期标签
    xtick_positions = x_indices[::step]
    xtick_labels = [d.strftime('%m-%d') for d in df_plot['date'].iloc[::step]]
    ax1.set_xticks(xtick_positions)
    ax1.set_xticklabels(xtick_labels, rotation=45, ha='right', fontsize=9)

    ax1.set_xlabel('日期', fontsize=11)
    ax1.set_ylabel('总分', fontsize=11, color='#2E86AB')
    ax1_twin.set_ylabel('当日涨跌幅 (%)', fontsize=11, color='#E63946')
    ax1.tick_params(axis='y', labelcolor='#2E86AB')
    ax1_twin.tick_params(axis='y', labelcolor='#E63946')
    ax1.set_title('总分趋势 vs 当日涨跌幅', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)

    # 合并图例
    lines = line1 + [line2]
    labels = [line1[0].get_label(), '当日涨跌幅']
    ax1.legend(lines, labels, loc='upper left', fontsize=9)

    # ========== 子图2: 5个分项得分堆叠面积图 ==========
    ax2 = axes[0, 1]

    # 准备堆叠数据
    categories = ['趋势分', '动量分', '波动分', '成交量分', '形态分']
    category_cols = ['trend_score', 'momentum_score', 'volatility_score', 'volume_score', 'pattern_score']
    colors = ['#06D6A0', '#118AB2', '#073B4C', '#FFD166', '#EF476F']

    # 绘制堆叠面积图
    ax2.stackplot(df_plot['date'],
                  [df_plot[col] for col in category_cols],
                  labels=categories,
                  colors=colors,
                  alpha=0.7)

    ax2.set_xlabel('日期', fontsize=11)
    ax2.set_ylabel('得分', fontsize=11)
    ax2.set_title('分项得分构成', fontsize=12, fontweight='bold')
    ax2.legend(loc='upper left', fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=1)

    # ========== 子图3: 得分 vs 次日涨跌幅（预判性分析）==========
    ax3 = axes[1, 0]
    ax3_twin = ax3.twinx()

    # 准备预判性对齐的数据：第n-1天的得分对应第n天的涨跌幅
    # 即：昨天的得分预测今天的涨跌
    df_predict = df_plot.copy()
    # 将涨跌幅向前移动一位，使其对应前一天的得分
    df_predict['next_day_return'] = df_predict['daily_return'].shift(-1)

    # 过滤掉没有次日涨跌幅的数据（最后一天）
    df_predict_valid = df_predict[df_predict['next_day_return'].notna()].copy()
    x_indices_predict = np.arange(len(df_predict_valid))

    # 绘制总分
    line1_predict = ax3.plot(x_indices_predict, df_predict_valid['total_score'],
                             color='#2E86AB', linewidth=2, marker='o', markersize=4,
                             label='总分')
    ax3.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.5)
    ax3.axhline(y=5, color='green', linestyle=':', linewidth=1, alpha=0.5, label='看多线(+5)')
    ax3.axhline(y=-5, color='red', linestyle=':', linewidth=1, alpha=0.5, label='看空线(-5)')
    ax3.fill_between(x_indices_predict, 0, df_predict_valid['total_score'],
                     where=(df_predict_valid['total_score'] >= 0), alpha=0.2, color='green', label='正分区域')
    ax3.fill_between(x_indices_predict, 0, df_predict_valid['total_score'],
                     where=(df_predict_valid['total_score'] < 0), alpha=0.2, color='red', label='负分区域')

    # 绘制次日涨跌幅（柱状图）- 涨红跌绿
    bar_colors_predict = ['#FF3333' if x >= 0 else '#00CC00' for x in df_predict_valid['next_day_return']]
    line2_predict = ax3_twin.bar(x_indices_predict, df_predict_valid['next_day_return'],
                                  color=bar_colors_predict, alpha=0.6, width=0.8,
                                  label='次日涨跌幅')

    # 在柱子上标注涨跌幅数值
    for idx, val in zip(x_indices_predict, df_predict_valid['next_day_return']):
        if pd.notna(val):
            if val >= 0:
                va = 'bottom'
                y_pos = val
            else:
                va = 'top'
                y_pos = val
            ax3_twin.text(idx, y_pos, f'{val:.1f}%',
                         ha='center', va=va, fontsize=7,
                         color='black', rotation=0)

    # 添加0%基准线
    ax3_twin.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.5)

    # 对齐两个y轴的0点
    score_max_predict = max(abs(df_predict_valid['total_score'].min()), abs(df_predict_valid['total_score'].max()))
    return_max_predict = max(abs(df_predict_valid['next_day_return'].min()), abs(df_predict_valid['next_day_return'].max()))
    y_max_predict = max(score_max_predict, return_max_predict) * 1.3
    ax3.set_ylim(-y_max_predict, y_max_predict)
    ax3_twin.set_ylim(-y_max_predict, y_max_predict)

    # 在总分点位下方10%处标注得分
    y_range_predict = y_max_predict * 2  # 总的y轴范围
    offset_predict = y_range_predict * 0.10  # 10%的偏移量
    for idx, score in zip(x_indices_predict, df_predict_valid['total_score']):
        # 标注位置在得分点下方10%
        y_pos = score - offset_predict
        ax3.text(idx, y_pos, f'{score:+.0f}',
                ha='center', va='top', fontsize=7,
                color='#2E86AB', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#2E86AB', alpha=0.7))

    # 设置x轴刻度标签为日期（每隔几个显示）
    step_predict = max(1, len(df_predict_valid) // 15)  # 显示约15个日期标签
    xtick_positions_predict = x_indices_predict[::step_predict]
    xtick_labels_predict = [d.strftime('%m-%d') for d in df_predict_valid['date'].iloc[::step_predict]]
    ax3.set_xticks(xtick_positions_predict)
    ax3.set_xticklabels(xtick_labels_predict, rotation=45, ha='right', fontsize=9)

    ax3.set_xlabel('日期', fontsize=11)
    ax3.set_ylabel('总分', fontsize=11, color='#2E86AB')
    ax3_twin.set_ylabel('次日涨跌幅 (%)', fontsize=11, color='#E63946')
    ax3.tick_params(axis='y', labelcolor='#2E86AB')
    ax3_twin.tick_params(axis='y', labelcolor='#E63946')
    ax3.set_title('得分预判性分析（第N天得分 vs 第N+1天涨跌）', fontsize=12, fontweight='bold')
    ax3.grid(True, alpha=0.3)

    # 合并图例
    lines_predict = line1_predict + [line2_predict]
    labels_predict = [line1_predict[0].get_label(), '次日涨跌幅']
    ax3.legend(lines_predict, labels_predict, loc='upper left', fontsize=9)

    # ========== 子图4: 五个子得分 vs 次日涨跌幅（预判性分析）==========
    ax4 = axes[1, 1]
    ax4_twin = ax4.twinx()

    # 准备预判性对齐的数据（与左下角相同的逻辑）
    df_predict_sub = df_plot.copy()
    df_predict_sub['next_day_return'] = df_predict_sub['daily_return'].shift(-1)
    df_predict_sub_valid = df_predict_sub[df_predict_sub['next_day_return'].notna()].copy()
    x_indices_sub = np.arange(len(df_predict_sub_valid))

    # 绘制五个子得分折线图
    score_types = [
        ('trend_score', '趋势分', '#06D6A0'),
        ('momentum_score', '动量分', '#118AB2'),
        ('volatility_score', '波动分', '#073B4C'),
        ('volume_score', '成交量分', '#FFD166'),
        ('pattern_score', '形态分', '#EF476F')
    ]

    for score_col, score_label, color in score_types:
        ax4.plot(x_indices_sub, df_predict_sub_valid[score_col],
                color=color, linewidth=2, marker='o', markersize=3,
                label=score_label, alpha=0.8)

    ax4.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.5)
    ax4.legend(loc='upper left', fontsize=9)

    # 绘制次日涨跌幅（柱状图）- 涨红跌绿
    bar_colors_sub = ['#FF3333' if x >= 0 else '#00CC00' for x in df_predict_sub_valid['next_day_return']]
    line2_sub = ax4_twin.bar(x_indices_sub, df_predict_sub_valid['next_day_return'],
                              color=bar_colors_sub, alpha=0.6, width=0.8,
                              label='次日涨跌幅')

    # 在柱子上标注涨跌幅数值
    for idx, val in zip(x_indices_sub, df_predict_sub_valid['next_day_return']):
        if pd.notna(val):
            if val >= 0:
                va = 'bottom'
                y_pos = val
            else:
                va = 'top'
                y_pos = val
            ax4_twin.text(idx, y_pos, f'{val:.1f}%',
                         ha='center', va=va, fontsize=7,
                         color='black', rotation=0)

    # 添加0%基准线
    ax4_twin.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.5)

    # 对齐两个y轴的0点
    # 计算五个子得分的最大绝对值
    score_max_sub = max([
        abs(df_predict_sub_valid[col].min())
        for col, _, _ in score_types
    ] + [
        abs(df_predict_sub_valid[col].max())
        for col, _, _ in score_types
    ])
    return_max_sub = max(abs(df_predict_sub_valid['next_day_return'].min()),
                         abs(df_predict_sub_valid['next_day_return'].max()))
    y_max_sub = max(score_max_sub, return_max_sub) * 1.3
    ax4.set_ylim(-y_max_sub, y_max_sub)
    ax4_twin.set_ylim(-y_max_sub, y_max_sub)

    # 设置x轴刻度标签为日期
    step_sub = max(1, len(df_predict_sub_valid) // 15)
    xtick_positions_sub = x_indices_sub[::step_sub]
    xtick_labels_sub = [d.strftime('%m-%d') for d in df_predict_sub_valid['date'].iloc[::step_sub]]
    ax4.set_xticks(xtick_positions_sub)
    ax4.set_xticklabels(xtick_labels_sub, rotation=45, ha='right', fontsize=9)

    ax4.set_xlabel('日期', fontsize=11)
    ax4.set_ylabel('子得分', fontsize=11, color='black')
    ax4_twin.set_ylabel('次日涨跌幅 (%)', fontsize=11, color='#E63946')
    ax4.tick_params(axis='y', labelcolor='black')
    ax4_twin.tick_params(axis='y', labelcolor='#E63946')
    ax4.set_title('五个子得分 vs 次日涨跌幅（预判性分析）', fontsize=12, fontweight='bold')
    ax4.grid(True, alpha=0.3)

    # 调整布局
    plt.tight_layout()

    # 保存图表
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()

    logger.info(f"✓ 可视化图表已保存: {filepath}")
    return filepath


# ==================== 主程序 ====================

def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(description='单股票滚动窗口打分系统')

    parser.add_argument('--code', type=str, required=True,
                       help='股票代码（如 000001.SZ）')
    parser.add_argument('--name', type=str, default=None,
                       help='股票名称（可选）')
    parser.add_argument('--end-date', type=str, default=None,
                       help='结束日期（YYYYMMDD格式，默认今天）')
    parser.add_argument('--num-windows', type=int, default=30,
                       help='窗口数量（默认30个交易日）')
    parser.add_argument('--indicator-window', type=int, default=60,
                       help='指标计算窗口（默认60天，建议不小于60）')
    parser.add_argument('--use-local-db', action='store_true',
                       help='使用本地数据库，速度更快（默认使用在线Tushare，需要配置database模块）')
    parser.add_argument('--output-dir', type=str, default=OUTPUT_DIR,
                       help=f'输出目录（默认: {OUTPUT_DIR}）')

    # 数据库相关参数
    parser.add_argument('--force-recalculate', action='store_true',
                       help='强制重新计算，忽略数据库缓存')
    parser.add_argument('--clear-cache', action='store_true',
                       help='清除该股票的数据库缓存后重新计算')
    parser.add_argument('--db-info', action='store_true',
                       help='显示数据库中该股票的打分数据信息')
    parser.add_argument('--db-export', action='store_true',
                       help='从数据库导出打分数据到CSV（不重新计算）')

    args = parser.parse_args()

    # 参数验证
    if args.indicator_window < 60:
        logger.warning(f"指标计算窗口({args.indicator_window})小于建议值60天，可能导致指标不准确")

    # 创建输出目录
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    try:
        # 创建分析器
        analyzer = RollingScoreAnalyzer(
            stock_code=args.code,
            stock_name=args.name,
            use_local_db=args.use_local_db
        )

        # 处理数据库信息查询
        if args.db_info:
            if analyzer.score_repo:
                info = analyzer.score_repo.get_score_info(args.code)
                if info:
                    print("\n" + "=" * 60)
                    print(f"数据库打分信息")
                    print("=" * 60)
                    print(f"股票代码: {info['ts_code']}")
                    print(f"记录数量: {info['record_count']} 条")
                    print(f"日期范围: {info['date_range'][0]} - {info['date_range'][1]}")
                    print(f"平均得分: {info['avg_score']:+.2f}" if info['avg_score'] else "平均得分: N/A")
                    print(f"最后更新: {info['last_update']}")
                    print("=" * 60)
                else:
                    print(f"\n{args.code} 无打分数据")
            else:
                print("\n⚠️  数据库仓库不可用")
            sys.exit(0)

        # 处理数据库导出
        if args.db_export:
            if analyzer.score_repo:
                df_cached = analyzer.score_repo.load_scores(args.code)
                if df_cached is not None and not df_cached.empty:
                    csv_path = save_csv(df_cached, args.code, args.output_dir)
                    print(f"\n✓ 已从数据库导出 {len(df_cached)} 条记录到: {csv_path}")
                else:
                    print(f"\n{args.code} 无打分数据可导出")
            else:
                print("\n⚠️  数据库仓库不可用")
            sys.exit(0)

        # 处理清除缓存
        if args.clear_cache:
            if analyzer.score_repo:
                logger.info(f"\n清除 {args.code} 的数据库缓存...")
                analyzer.score_repo.delete_scores(args.code)
            else:
                logger.warning("\n⚠️  数据库仓库不可用，无法清除缓存")

        # 计算滚动窗口得分
        df_results = analyzer.calculate_rolling_scores(
            end_date=args.end_date,
            num_windows=args.num_windows,
            indicator_window=args.indicator_window,
            force_recalculate=args.force_recalculate or args.clear_cache
        )

        if df_results is None or df_results.empty:
            logger.error("计算失败，退出程序")
            sys.exit(1)

        # 识别信号
        df_results = analyzer.identify_signals(df_results)

        logger.info("\n" + "=" * 80)
        logger.info("开始生成输出文件...")
        logger.info("=" * 80)

        # 保存CSV
        csv_path = save_csv(df_results, args.code, args.output_dir)

        # 生成文本报告
        report_path = generate_text_report(
            df_results,
            args.code,
            args.name or args.code,
            args.output_dir
        )

        # 生成图表
        chart_path = generate_charts(
            df_results,
            args.code,
            args.name or args.code,
            args.output_dir
        )

        # 总结
        logger.info("\n" + "=" * 80)
        logger.info("✅ 所有任务完成！")
        logger.info("=" * 80)
        logger.info(f"股票: {args.code} ({args.name or args.code})")
        logger.info(f"分析周期: {df_results['date'].min()} 至 {df_results['date'].max()}")
        logger.info(f"输出文件:")
        logger.info(f"  📊 CSV数据: {csv_path}")
        logger.info(f"  📄 文本报告: {report_path}")
        logger.info(f"  📈 可视化图表: {chart_path}")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
