#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基本面分析脚本 - Fundamental Analysis Script
使用Tushare获取财务数据，计算同比环比指标
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple
import warnings

import pandas as pd
import tushare as ts
import matplotlib.pyplot as plt
import matplotlib
from tabulate import tabulate

# 配置中文字体支持
# macOS系统使用PingFang SC或STHeiti，Windows使用SimHei，Linux使用WenQuanYi
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'STHeiti', 'Heiti TC', 'Arial Unicode MS', 'SimHei', 'Microsoft YaHei', 'WenQuanYi Zen Hei']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

warnings.filterwarnings('ignore')

# 路径配置
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 输出目录
OUTPUT_DIR = os.path.join(project_root, 'fundamental_results')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class FundamentalDataFetcher:
    """基本面数据获取类"""

    def __init__(self):
        """初始化Tushare API"""
        self.pro = self._init_tushare()

    def _init_tushare(self):
        """初始化Tushare，从token.txt读取token"""
        token_file = os.path.join(project_root, 'token.txt')

        try:
            with open(token_file, 'r') as f:
                ts_token = f.read().strip()

            if not ts_token:
                raise ValueError("token.txt文件为空")

            ts.set_token(ts_token)
            pro = ts.pro_api()
            logger.info("Tushare API初始化成功")
            return pro

        except FileNotFoundError:
            logger.error(f"未找到token文件: {token_file}")
            raise
        except Exception as e:
            logger.error(f"初始化Tushare失败: {e}")
            raise

    def get_stock_name(self, ts_code: str) -> str:
        """
        获取股票名称

        Args:
            ts_code: 股票代码，如 '600519.SH'

        Returns:
            股票名称，如 '贵州茅台'；如果获取失败则返回代码本身
        """
        try:
            # 使用stock_basic接口获取股票基本信息
            df = self.pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
            if not df.empty:
                stock_name = df.iloc[0]['name']
                logger.info(f"获取股票名称成功: {ts_code} -> {stock_name}")
                return stock_name
            else:
                logger.warning(f"未找到股票 {ts_code} 的名称信息")
                return ts_code
        except Exception as e:
            logger.warning(f"获取股票名称失败: {e}，使用代码 {ts_code}")
            return ts_code

    def get_recent_quarters(self, num_quarters: int = 4) -> List[str]:
        """
        获取最近N个季度的报告期

        Args:
            num_quarters: 季度数量，默认4

        Returns:
            季度列表，格式如 ['20240930', '20240630', '20240331', '20231231']
        """
        current_date = datetime.now()
        quarters = []

        year = current_date.year
        month = current_date.month

        # 确定最近已公布的季度（假设季报在季度结束后1个月内公布）
        # Q1 (3/31) 通常4月底公布，Q2 (6/30) 通常8月底公布
        # Q3 (9/30) 通常10月底公布，Q4 (12/31) 通常次年4月底公布

        if month >= 11:  # 11月开始，Q3数据应该已公布
            quarter_ends = ['0930', '0630', '0331', '1231']
            years = [year, year, year, year - 1]
        elif month >= 8:  # 8月开始，Q2数据应该已公布
            quarter_ends = ['0630', '0331', '1231', '0930']
            years = [year, year, year - 1, year - 1]
        elif month >= 5:  # 5月开始，Q1数据和去年年报应该已公布
            quarter_ends = ['0331', '1231', '0930', '0630']
            years = [year, year - 1, year - 1, year - 1]
        else:  # 1-4月，只有去年的数据
            quarter_ends = ['1231', '0930', '0630', '0331']
            years = [year - 1, year - 1, year - 1, year - 1]

        # 生成所需数量的季度
        for i in range(min(num_quarters, len(quarter_ends))):
            quarters.append(f"{years[i]}{quarter_ends[i]}")

        # 如果需要更多季度，继续往前推
        if num_quarters > 4:
            last_date = quarters[-1]
            last_year = int(last_date[:4])
            last_q_end = last_date[4:]

            quarter_list = ['0331', '0630', '0930', '1231']
            q_idx = quarter_list.index(last_q_end)

            for i in range(num_quarters - 4):
                q_idx -= 1
                if q_idx < 0:
                    q_idx = 3
                    last_year -= 1
                quarters.append(f"{last_year}{quarter_list[q_idx]}")

        logger.info(f"生成季度列表: {quarters[:num_quarters]}")
        return quarters[:num_quarters]

    def fetch_financial_data(self, ts_code: str, quarters: List[str]) -> Dict[str, pd.DataFrame]:
        """
        获取指定股票的财务数据

        Args:
            ts_code: 股票代码，如 '000001.SZ'
            quarters: 季度列表

        Returns:
            包含利润表、资产负债表、财务指标的字典
        """
        try:
            # 使用循环逐个获取每个季度的数据，避免遗漏端点季度
            income_list = []
            balance_list = []
            indicator_list = []
            expense_list = []

            for period in quarters:
                # 获取利润表数据
                income_temp = self.pro.income(
                    ts_code=ts_code,
                    period=period,
                    fields='ts_code,end_date,total_revenue,revenue,total_operate_cost,operate_profit,total_profit,n_income'
                )
                if not income_temp.empty:
                    income_list.append(income_temp)

                # 获取资产负债表数据
                balance_temp = self.pro.balancesheet(
                    ts_code=ts_code,
                    period=period,
                    fields='ts_code,end_date,total_assets,total_liab,total_cur_assets,total_cur_liab'
                )
                if not balance_temp.empty:
                    balance_list.append(balance_temp)

                # 获取财务指标数据
                indicator_temp = self.pro.fina_indicator(
                    ts_code=ts_code,
                    period=period,
                    fields='ts_code,end_date,grossprofit_margin,netprofit_margin,roe,roa,'
                           'debt_to_assets,current_ratio,salescash_to_or,ocf_to_or'
                )
                if not indicator_temp.empty:
                    indicator_list.append(indicator_temp)

                # 获取业务费用明细
                expense_temp = self.pro.income(
                    ts_code=ts_code,
                    period=period,
                    fields='ts_code,end_date,sell_exp,admin_exp,rd_exp,total_revenue'
                )
                if not expense_temp.empty:
                    expense_list.append(expense_temp)

            # 合并所有季度的数据
            income_df = pd.concat(income_list, ignore_index=True) if income_list else pd.DataFrame()
            balance_df = pd.concat(balance_list, ignore_index=True) if balance_list else pd.DataFrame()
            indicator_df = pd.concat(indicator_list, ignore_index=True) if indicator_list else pd.DataFrame()
            expense_df = pd.concat(expense_list, ignore_index=True) if expense_list else pd.DataFrame()

            logger.info(f"成功获取 {ts_code} 的财务数据 (利润表:{len(income_df)}季度, 指标:{len(indicator_df)}季度)")

            return {
                'income': income_df,
                'balance': balance_df,
                'indicator': indicator_df,
                'expense': expense_df
            }

        except Exception as e:
            logger.error(f"获取 {ts_code} 财务数据失败: {e}")
            return None


class FundamentalAnalyzer:
    """基本面分析类"""

    def __init__(self, ts_code: str, data: Dict[str, pd.DataFrame], stock_name: str = None):
        """
        初始化分析器

        Args:
            ts_code: 股票代码
            data: 财务数据字典
            stock_name: 股票名称（可选）
        """
        self.ts_code = ts_code
        self.stock_name = stock_name if stock_name else ts_code
        self.data = data
        self.analysis_result = None

    def calculate_metrics(self) -> pd.DataFrame:
        """
        计算并整合所有财务指标

        Returns:
            包含所有指标的DataFrame
        """
        if not self.data or not all(k in self.data for k in ['income', 'indicator', 'expense']):
            logger.error(f"{self.ts_code} 数据不完整")
            return None

        income_df = self.data['income'].copy()
        indicator_df = self.data['indicator'].copy()
        expense_df = self.data['expense'].copy()
        balance_df = self.data['balance'].copy()

        if income_df.empty or indicator_df.empty or expense_df.empty:
            logger.warning(f"{self.ts_code} 缺少财务数据 (income:{len(income_df)}, indicator:{len(indicator_df)}, expense:{len(expense_df)})")
            return None

        # 去重（有些API返回重复数据）
        income_df = income_df.drop_duplicates(subset=['end_date'], keep='first')
        indicator_df = indicator_df.drop_duplicates(subset=['end_date'], keep='first')
        expense_df = expense_df.drop_duplicates(subset=['end_date'], keep='first')
        balance_df = balance_df.drop_duplicates(subset=['end_date'], keep='first')

        # 以报告期为key合并所有数据
        result = indicator_df[['end_date', 'grossprofit_margin', 'netprofit_margin',
                               'roe', 'roa', 'debt_to_assets', 'current_ratio',
                               'salescash_to_or', 'ocf_to_or']].copy()

        # 重命名列
        result = result.rename(columns={
            'end_date': '报告期',
            'grossprofit_margin': '毛利率(%)',
            'netprofit_margin': '净利率(%)',
            'roe': 'ROE(%)',
            'roa': 'ROA(%)',
            'debt_to_assets': '资产负债率(%)',
            'current_ratio': '流动比率',
            'salescash_to_or': '销售现金比率(%)',
            'ocf_to_or': '经营现金流比率(%)'
        })

        # 合并营业收入（单位：元 -> 亿元，除以1亿）
        income_merge = income_df[['end_date', 'total_revenue']].copy()
        income_merge['营业收入(亿元)'] = income_merge['total_revenue'] / 100000000
        result = result.merge(income_merge[['end_date', '营业收入(亿元)']],
                             left_on='报告期', right_on='end_date', how='left')
        result = result.drop('end_date', axis=1)

        # 合并费用数据
        expense_merge = expense_df[['end_date', 'sell_exp', 'admin_exp', 'rd_exp', 'total_revenue']].copy()
        expense_merge['销售费用率(%)'] = (expense_merge['sell_exp'] / expense_merge['total_revenue'] * 100)
        expense_merge['管理费用率(%)'] = (expense_merge['admin_exp'] / expense_merge['total_revenue'] * 100)
        expense_merge['研发费用率(%)'] = (expense_merge['rd_exp'] / expense_merge['total_revenue'] * 100)

        result = result.merge(expense_merge[['end_date', '销售费用率(%)', '管理费用率(%)', '研发费用率(%)']],
                             left_on='报告期', right_on='end_date', how='left')
        result = result.drop('end_date', axis=1)

        # 调整列顺序
        column_order = ['报告期', '营业收入(亿元)', '毛利率(%)', '净利率(%)',
                       '销售费用率(%)', '管理费用率(%)', '研发费用率(%)',
                       'ROE(%)', 'ROA(%)', '资产负债率(%)', '流动比率',
                       '销售现金比率(%)', '经营现金流比率(%)']

        result = result[column_order]

        # 按报告期降序排列（最新的在最上面）
        result = result.sort_values('报告期', ascending=False).reset_index(drop=True)

        # 检查数据完整性，提示哪些季度数据不完整
        for idx, row in result.iterrows():
            quarter = row['报告期']
            # 检查关键字段是否为空
            if pd.isna(row['营业收入(亿元)']):
                logger.warning(f"{self.ts_code} {quarter} 季度的利润表数据尚未发布（营业收入为空），部分指标将显示为NaN")

        return result

    def calculate_growth_rates(self, metrics_df: pd.DataFrame) -> pd.DataFrame:
        """
        计算同比和环比增长率

        Args:
            metrics_df: 指标数据

        Returns:
            包含增长率的DataFrame
        """
        if metrics_df is None or len(metrics_df) < 2:
            logger.warning(f"{self.ts_code} 数据不足，无法计算增长率")
            return None

        # 数值列（排除报告期）
        numeric_cols = [col for col in metrics_df.columns if col != '报告期']

        growth_df = pd.DataFrame()
        growth_df['报告期'] = metrics_df['报告期'].values

        # 计算环比增长率 (QoQ: Quarter over Quarter)
        for col in numeric_cols:
            qoq_col = f"{col}_环比(%)"
            growth_df[qoq_col] = None

            for i in range(len(metrics_df) - 1):
                current = metrics_df.iloc[i][col]
                previous = metrics_df.iloc[i + 1][col]

                if pd.notna(current) and pd.notna(previous) and previous != 0:
                    growth_rate = ((current - previous) / abs(previous)) * 100
                    growth_df.at[i, qoq_col] = round(growth_rate, 2)

        # 计算同比增长率 (YoY: Year over Year)
        for col in numeric_cols:
            yoy_col = f"{col}_同比(%)"
            growth_df[yoy_col] = None

            if len(metrics_df) >= 5:  # 需要至少5个季度才能计算同比
                for i in range(len(metrics_df) - 4):
                    current = metrics_df.iloc[i][col]
                    year_ago = metrics_df.iloc[i + 4][col]

                    if pd.notna(current) and pd.notna(year_ago) and year_ago != 0:
                        growth_rate = ((current - year_ago) / abs(year_ago)) * 100
                        growth_df.at[i, yoy_col] = round(growth_rate, 2)

        return growth_df

    def analyze(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        执行完整分析

        Returns:
            (指标数据, 增长率数据)
        """
        metrics_df = self.calculate_metrics()
        if metrics_df is None:
            return None, None

        growth_df = self.calculate_growth_rates(metrics_df)

        self.analysis_result = {
            'metrics': metrics_df,
            'growth': growth_df
        }

        return metrics_df, growth_df


class ResultOutputter:
    """结果输出类"""

    def __init__(self, ts_code: str, metrics_df: pd.DataFrame, growth_df: pd.DataFrame, stock_name: str = None):
        """
        初始化输出器

        Args:
            ts_code: 股票代码
            metrics_df: 指标数据
            growth_df: 增长率数据
            stock_name: 股票名称（可选）
        """
        self.ts_code = ts_code
        self.stock_name = stock_name if stock_name else ts_code
        self.metrics_df = metrics_df
        self.growth_df = growth_df
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    def print_to_console(self):
        """打印到控制台"""
        print(f"\n{'=' * 100}")
        print(f"股票: {self.ts_code} ({self.stock_name}) - 基本面分析报告")
        print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 100}\n")

        # 打印指标数据
        print("【财务指标数据】")
        print(tabulate(self.metrics_df, headers='keys', tablefmt='grid', showindex=False, floatfmt='.2f'))

        # 打印增长率数据（仅显示核心指标的增长率）
        if self.growth_df is not None and not self.growth_df.empty:
            print(f"\n{'=' * 100}\n")
            print("【同比/环比增长率 - 核心指标】")

            # 选择核心指标的增长率列
            core_growth_cols = ['报告期']
            for col in ['营业收入(亿元)', '毛利率(%)', '净利率(%)', 'ROE(%)', 'ROA(%)']:
                qoq = f"{col}_环比(%)"
                yoy = f"{col}_同比(%)"
                if qoq in self.growth_df.columns:
                    core_growth_cols.append(qoq)
                if yoy in self.growth_df.columns:
                    core_growth_cols.append(yoy)

            growth_display = self.growth_df[core_growth_cols]
            print(tabulate(growth_display, headers='keys', tablefmt='grid', showindex=False, floatfmt='.2f'))

        print(f"\n{'=' * 100}\n")

    def save_to_txt(self):
        """保存到TXT文件"""
        # 文件名包含股票名称
        safe_name = self.stock_name.replace(' ', '_')  # 替换空格
        filename = f"{self.ts_code}_{safe_name}_{self.timestamp}.txt"
        filepath = os.path.join(OUTPUT_DIR, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"{'=' * 100}\n")
            f.write(f"股票: {self.ts_code} ({self.stock_name}) - 基本面分析详细报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'=' * 100}\n\n")

            # 写入指标数据
            f.write("【财务指标数据】\n")
            f.write(tabulate(self.metrics_df, headers='keys', tablefmt='grid', showindex=False, floatfmt='.2f'))
            f.write("\n\n")

            # 写入完整增长率数据
            if self.growth_df is not None and not self.growth_df.empty:
                f.write(f"{'=' * 100}\n\n")
                f.write("【同比/环比增长率 - 完整数据】\n")
                f.write(tabulate(self.growth_df, headers='keys', tablefmt='grid', showindex=False, floatfmt='.2f'))
                f.write("\n\n")

            f.write(f"{'=' * 100}\n")

        logger.info(f"详细报告已保存至: {filepath}")
        return filepath

    def plot_trends(self):
        """绘制趋势图 - 折线图显示数值，柱状图显示环比"""
        if self.metrics_df is None or len(self.metrics_df) < 2:
            logger.warning(f"{self.ts_code} 数据不足，无法绘制趋势图")
            return

        # 设置全局样式（先设置样式）
        plt.style.use('seaborn-v0_8-darkgrid')

        # 设置中文字体 - 在样式之后设置，避免被覆盖
        import matplotlib.font_manager as fm
        from matplotlib.font_manager import FontProperties

        # 查找系统中可用的中文字体
        font_list = [f.name for f in fm.fontManager.ttflist]
        chinese_font = None
        for font_name in ['PingFang SC', 'Heiti SC', 'STHeiti', 'Hiragino Sans GB', 'Arial Unicode MS']:
            if font_name in font_list:
                chinese_font = font_name
                break

        if chinese_font:
            # 创建字体属性对象
            font_prop = FontProperties(family=chinese_font)
            # 强制设置中文字体，覆盖seaborn样式
            plt.rcParams['font.sans-serif'] = [chinese_font]
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['axes.unicode_minus'] = False
            logger.info(f"使用中文字体: {chinese_font}")
        else:
            font_prop = FontProperties()
            logger.warning("未找到合适的中文字体，可能导致中文显示异常")

        # 创建图表 (3行2列)
        fig, axes = plt.subplots(3, 2, figsize=(20, 15))
        fig.patch.set_facecolor('#f8f9fa')

        # 主标题样式优化 - 包含股票名称
        title_text = f'{self.ts_code} {self.stock_name} 基本面指标趋势分析'
        fig.suptitle(title_text,
                     fontsize=18, fontweight='bold', y=0.995,
                     color='#2c3e50', family='sans-serif')

        # 副标题
        fig.text(0.5, 0.97, '折线图=指标数值 | 柱状图=环比增长率',
                ha='center', fontsize=11, color='#7f8c8d', style='italic')

        quarters = self.metrics_df['报告期'].values[::-1]  # 反转，使时间从左到右
        x_pos = range(len(quarters))  # 使用数值位置避免日期解析问题

        # 优化的配色方案
        colors = {
            'revenue': '#3498db',      # 蓝色 - 营业收入
            'gross': '#9b59b6',        # 紫色 - 毛利率
            'net': '#e67e22',          # 橙色 - 净利率
            'roe': '#27ae60',          # 绿色 - ROE
            'roa': '#e74c3c',          # 红色 - ROA
            'sales_exp': '#3498db',    # 蓝色 - 销售费用率
            'admin_exp': '#e67e22',    # 橙色 - 管理费用率
            'rd_exp': '#27ae60',       # 绿色 - 研发费用率
            'bar_positive': '#2ecc71', # 亮绿 - 增长
            'bar_negative': '#e74c3c', # 亮红 - 下降
        }

        # 辅助函数：创建双Y轴图表
        def create_dual_axis_plot(ax, metric_name, metric_data, growth_col,
                                  line_color, ylabel_left, ylabel_right):
            """
            创建双Y轴图表
            左轴：折线图显示指标数值
            右轴：柱状图显示环比增长率（红绿色）
            """
            # 过滤NaN值
            valid_mask = ~pd.isna(metric_data)
            valid_x = [x for x, v in zip(x_pos, valid_mask) if v]
            valid_quarters_display = [q for q, v in zip(quarters, valid_mask) if v]
            valid_data = [d for d, v in zip(metric_data, valid_mask) if v]

            if len(valid_data) == 0:
                ax.text(0.5, 0.5, '数据不足', ha='center', va='center',
                       transform=ax.transAxes, fontsize=14, color='gray')
                return

            # 左轴：折线图（数值）- 美化样式
            line = ax.plot(valid_x, valid_data, marker='o', linewidth=3, markersize=10,
                          color=line_color, label=f'{metric_name}',
                          markeredgecolor='white', markeredgewidth=2,
                          alpha=0.9, zorder=3)

            # 在数据点上标注数值 - 优化样式
            for i, (x, y) in enumerate(zip(valid_x, valid_data)):
                # 格式化数值：如果是大数字（如营业收入），保留2位小数；否则保留1位
                if abs(y) >= 100:
                    label_text = f'{y:.1f}'
                else:
                    label_text = f'{y:.1f}'

                ax.annotate(label_text,
                           xy=(x, y),
                           xytext=(0, 10),  # 向上偏移10个点
                           textcoords='offset points',
                           ha='center',
                           va='bottom',
                           fontsize=9,
                           color=line_color,
                           fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.4',
                                   facecolor='white',
                                   edgecolor=line_color,
                                   linewidth=1.5,
                                   alpha=0.95),
                           zorder=4)

            # 美化左Y轴
            ax.set_ylabel(ylabel_left, fontsize=12, color=line_color,
                         fontweight='bold', labelpad=10)
            ax.tick_params(axis='y', labelcolor=line_color, labelsize=10, width=2)
            ax.spines['left'].set_color(line_color)
            ax.spines['left'].set_linewidth(2)

            # 美化X轴
            ax.set_xticks(x_pos)
            ax.set_xticklabels(quarters, rotation=45, ha='right', fontsize=10)
            ax.tick_params(axis='x', labelsize=10, width=2)

            # 网格线美化
            ax.grid(True, alpha=0.2, linestyle='--', linewidth=1, zorder=1)
            ax.set_axisbelow(True)

            # 右轴：柱状图（环比增长率）- 美化样式
            if self.growth_df is not None and growth_col in self.growth_df.columns:
                ax2 = ax.twinx()
                growth_data = self.growth_df[growth_col].values[::-1]

                # 准备柱状图数据（红绿色）
                valid_growth_mask = ~pd.isna(growth_data)
                valid_growth_x = [x for x, v in zip(x_pos, valid_growth_mask) if v]
                valid_growth = [d for d, v in zip(growth_data, valid_growth_mask) if v]
                bar_colors = [colors['bar_positive'] if v > 0 else colors['bar_negative']
                             for v in valid_growth]

                # 绘制柱状图 - 美化样式
                bars = ax2.bar(valid_growth_x, valid_growth,
                              alpha=0.35, color=bar_colors,
                              width=0.6, label='环比增长率',
                              edgecolor='white', linewidth=1.5,
                              zorder=2)

                # 在柱状图上标注数值
                for i, (x, y) in enumerate(zip(valid_growth_x, valid_growth)):
                    # 确定标注位置：正值在柱子上方，负值在柱子下方
                    if y > 0:
                        xytext = (0, 5)  # 正值向上偏移
                        va = 'bottom'
                    else:
                        xytext = (0, -5)  # 负值向下偏移
                        va = 'top'

                    # 格式化标注文本
                    label_text = f'{y:.1f}%'

                    # 根据正负值选择颜色
                    text_color = colors['bar_positive'] if y > 0 else colors['bar_negative']

                    ax2.annotate(label_text,
                               xy=(x, y),
                               xytext=xytext,
                               textcoords='offset points',
                               ha='center',
                               va=va,
                               fontsize=8,
                               color=text_color,
                               fontweight='bold',
                               bbox=dict(boxstyle='round,pad=0.3',
                                       facecolor='white',
                                       edgecolor=text_color,
                                       linewidth=1.2,
                                       alpha=0.9),
                               zorder=5)

                # 零线
                ax2.axhline(y=0, color='#34495e', linestyle='-',
                           linewidth=1.5, alpha=0.7, zorder=2)

                # 美化右Y轴
                ax2.set_ylabel(ylabel_right, fontsize=12, color='#34495e',
                              fontweight='bold', labelpad=10)
                ax2.tick_params(axis='y', labelcolor='#34495e', labelsize=10, width=2)
                ax2.spines['right'].set_color('#34495e')
                ax2.spines['right'].set_linewidth(2)

                # 图例 - 美化样式
                lines1, labels1 = ax.get_legend_handles_labels()
                lines2, labels2 = ax2.get_legend_handles_labels()
                legend = ax.legend(lines1 + lines2, labels1 + labels2,
                                  loc='upper left', fontsize=10,
                                  framealpha=0.95, edgecolor='#bdc3c7',
                                  fancybox=True, shadow=True)
                legend.get_frame().set_facecolor('#ecf0f1')
            else:
                legend = ax.legend(loc='upper left', fontsize=10,
                                  framealpha=0.95, edgecolor='#bdc3c7',
                                  fancybox=True, shadow=True)
                legend.get_frame().set_facecolor('#ecf0f1')

            # 美化边框
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['bottom'].set_linewidth(2)
            ax.spines['bottom'].set_color('#34495e')

        # 图1: 营业收入（折线+环比柱状图）
        ax1 = axes[0, 0]
        revenue = self.metrics_df['营业收入(亿元)'].values[::-1]
        create_dual_axis_plot(
            ax1, '营业收入', revenue, '营业收入(亿元)_环比(%)',
            colors['revenue'], '营业收入 (亿元)', '环比增长率 (%)'
        )
        ax1.set_title('营业收入趋势与环比增长', fontsize=13,
                     fontweight='bold', pad=15, color='#2c3e50')

        # 图2: 毛利率（折线+环比柱状图）
        ax2 = axes[0, 1]
        gross_margin = self.metrics_df['毛利率(%)'].values[::-1]
        create_dual_axis_plot(
            ax2, '毛利率', gross_margin, '毛利率(%)_环比(%)',
            colors['gross'], '毛利率 (%)', '环比变化 (百分点)'
        )
        ax2.set_title('毛利率趋势与环比变化', fontsize=13,
                     fontweight='bold', pad=15, color='#2c3e50')

        # 图3: 净利率（折线+环比柱状图）
        ax3 = axes[1, 0]
        net_margin = self.metrics_df['净利率(%)'].values[::-1]
        create_dual_axis_plot(
            ax3, '净利率', net_margin, '净利率(%)_环比(%)',
            colors['net'], '净利率 (%)', '环比变化 (百分点)'
        )
        ax3.set_title('净利率趋势与环比变化', fontsize=13,
                     fontweight='bold', pad=15, color='#2c3e50')

        # 图4: ROE（折线+环比柱状图）
        ax4 = axes[1, 1]
        roe = self.metrics_df['ROE(%)'].values[::-1]
        create_dual_axis_plot(
            ax4, 'ROE', roe, 'ROE(%)_环比(%)',
            colors['roe'], 'ROE (%)', '环比变化 (%)'
        )
        ax4.set_title('ROE趋势与环比变化', fontsize=13,
                     fontweight='bold', pad=15, color='#2c3e50')

        # 图5: 三费率对比（折线图，同一坐标系）
        ax5 = axes[2, 0]
        sales_exp = self.metrics_df['销售费用率(%)'].values[::-1]
        admin_exp = self.metrics_df['管理费用率(%)'].values[::-1]
        rd_exp = self.metrics_df['研发费用率(%)'].values[::-1]

        # 过滤有效数据
        valid_sales = [(x, v) for x, v in zip(x_pos, sales_exp) if pd.notna(v)]
        valid_admin = [(x, v) for x, v in zip(x_pos, admin_exp) if pd.notna(v)]
        valid_rd = [(x, v) for x, v in zip(x_pos, rd_exp) if pd.notna(v)]

        # 定义三费率的颜色
        expense_colors = {
            'sales': '#3498db',
            'admin': '#e67e22',
            'rd': '#27ae60'
        }

        if valid_sales:
            ax5.plot([x for x, _ in valid_sales], [v for _, v in valid_sales],
                    marker='o', label='销售费用率', linewidth=3, markersize=10,
                    color=expense_colors['sales'], markeredgecolor='white',
                    markeredgewidth=2, zorder=3)
            # 标注数值
            for x, v in valid_sales:
                ax5.annotate(f'{v:.1f}', xy=(x, v), xytext=(0, 10),
                           textcoords='offset points', ha='center', va='bottom',
                           fontsize=9, color=expense_colors['sales'], fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                                   edgecolor=expense_colors['sales'], linewidth=1.5, alpha=0.95),
                           zorder=4)

        if valid_admin:
            ax5.plot([x for x, _ in valid_admin], [v for _, v in valid_admin],
                    marker='s', label='管理费用率', linewidth=3, markersize=10,
                    color=expense_colors['admin'], markeredgecolor='white',
                    markeredgewidth=2, zorder=3)
            # 标注数值
            for x, v in valid_admin:
                ax5.annotate(f'{v:.1f}', xy=(x, v), xytext=(0, 10),
                           textcoords='offset points', ha='center', va='bottom',
                           fontsize=9, color=expense_colors['admin'], fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                                   edgecolor=expense_colors['admin'], linewidth=1.5, alpha=0.95),
                           zorder=4)

        if valid_rd:
            ax5.plot([x for x, _ in valid_rd], [v for _, v in valid_rd],
                    marker='^', label='研发费用率', linewidth=3, markersize=10,
                    color=expense_colors['rd'], markeredgecolor='white',
                    markeredgewidth=2, zorder=3)
            # 标注数值
            for x, v in valid_rd:
                ax5.annotate(f'{v:.1f}', xy=(x, v), xytext=(0, 10),
                           textcoords='offset points', ha='center', va='bottom',
                           fontsize=9, color=expense_colors['rd'], fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                                   edgecolor=expense_colors['rd'], linewidth=1.5, alpha=0.95),
                           zorder=4)

        ax5.set_title('三费率对比', fontsize=13, fontweight='bold',
                     pad=15, color='#2c3e50')
        ax5.set_ylabel('费用率 (%)', fontsize=11, fontweight='bold', color='#34495e')
        ax5.set_xticks(x_pos)
        ax5.set_xticklabels(quarters, rotation=45, ha='right', fontsize=10)
        ax5.legend(loc='best', fontsize=10, framealpha=0.95, shadow=True,
                  fancybox=True, edgecolor='#bdc3c7')
        ax5.grid(True, alpha=0.3, linestyle='--', linewidth=0.8, color='#95a5a6')
        ax5.spines['top'].set_visible(False)
        ax5.spines['right'].set_visible(False)
        ax5.spines['left'].set_color('#34495e')
        ax5.spines['left'].set_linewidth(1.5)
        ax5.spines['bottom'].set_color('#34495e')
        ax5.spines['bottom'].set_linewidth(1.5)
        ax5.tick_params(colors='#2c3e50', width=1.5)

        # 图6: ROA（折线+环比柱状图）
        ax6 = axes[2, 1]
        roa = self.metrics_df['ROA(%)'].values[::-1]
        create_dual_axis_plot(
            ax6, 'ROA', roa, 'ROA(%)_环比(%)',
            colors['roa'], 'ROA (%)', '环比变化 (%)'
        )
        ax6.set_title('ROA趋势与环比变化', fontsize=13,
                     fontweight='bold', pad=15, color='#2c3e50')

        plt.tight_layout(pad=2.0)

        # 保存图表 - 文件名包含股票名称
        safe_name = self.stock_name.replace(' ', '_')  # 替换空格
        chart_filename = f"{self.ts_code}_{safe_name}_{self.timestamp}_trends.png"
        chart_path = os.path.join(OUTPUT_DIR, chart_filename)
        plt.savefig(chart_path, dpi=200, bbox_inches='tight',
                   facecolor='#f8f9fa', edgecolor='none')
        logger.info(f"趋势图已保存至: {chart_path}")

        plt.close()
        return chart_path


def analyze_single_stock(ts_code: str, num_quarters: int = 4, save_txt: bool = False) -> bool:
    """
    分析单只股票

    Args:
        ts_code: 股票代码
        num_quarters: 获取的季度数量，默认4
        save_txt: 是否保存TXT报告，默认False

    Returns:
        是否成功
    """
    try:
        logger.info(f"开始分析 {ts_code} (获取最近{num_quarters}个季度)")

        # 获取数据
        fetcher = FundamentalDataFetcher()

        # 获取股票名称
        stock_name = fetcher.get_stock_name(ts_code)

        quarters = fetcher.get_recent_quarters(num_quarters=num_quarters)
        data = fetcher.fetch_financial_data(ts_code, quarters)

        if not data:
            logger.warning(f"{ts_code} 无法获取财务数据")
            return False

        # 分析
        analyzer = FundamentalAnalyzer(ts_code, data, stock_name)
        metrics_df, growth_df = analyzer.analyze()

        if metrics_df is None:
            logger.warning(f"{ts_code} 分析失败")
            return False

        # 输出结果
        outputter = ResultOutputter(ts_code, metrics_df, growth_df, stock_name)
        outputter.print_to_console()

        # 根据参数决定是否保存TXT
        if save_txt:
            outputter.save_to_txt()

        outputter.plot_trends()

        logger.info(f"{ts_code} ({stock_name}) 分析完成\n")
        return True

    except Exception as e:
        logger.error(f"{ts_code} 分析异常: {e}", exc_info=True)
        return False


def read_stock_pool(file_path: str) -> List[str]:
    """
    从文件读取股票池，支持行内注释

    Args:
        file_path: 文件路径

    Returns:
        股票代码列表

    文件格式示例：
        # 这是注释行
        600519.SH  # 贵州茅台
        000858.SZ
        688256.SH  # 寒武纪
    """
    stocks = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # 跳过空行和完整的注释行
                if not line or line.startswith('#'):
                    continue

                # 处理行内注释：提取 # 之前的内容作为股票代码
                if '#' in line:
                    code = line.split('#')[0].strip()
                else:
                    code = line.strip()

                # 只添加非空的股票代码
                if code:
                    stocks.append(code)

        logger.info(f"从 {file_path} 读取到 {len(stocks)} 只股票")
        return stocks

    except Exception as e:
        logger.error(f"读取股票池文件失败: {e}")
        return []


def batch_analyze(stock_list: List[str], max_workers: int = 4, num_quarters: int = 4, save_txt: bool = False):
    """
    批量分析股票

    Args:
        stock_list: 股票代码列表
        max_workers: 最大工作进程数
        num_quarters: 获取的季度数量，默认4
        save_txt: 是否保存TXT报告，默认False
    """
    total = len(stock_list)
    success_count = 0
    fail_count = 0

    logger.info(f"开始批量分析，共 {total} 只股票，使用 {max_workers} 个进程，每只股票获取 {num_quarters} 个季度")

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(analyze_single_stock, ts_code, num_quarters, save_txt): ts_code for ts_code in stock_list}

        for future in as_completed(futures):
            ts_code = futures[future]
            try:
                success = future.result()
                if success:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"{ts_code} 处理异常: {e}")
                fail_count += 1

    logger.info(f"\n批量分析完成！成功: {success_count}, 失败: {fail_count}, 总计: {total}")
    logger.info(f"结果保存在: {OUTPUT_DIR}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='基本面分析脚本 - 获取财务数据并计算同比环比',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  单只股票 (默认4个季度):
    python fundamental_analysis.py 600519.SH

  单只股票 (指定6个季度):
    python fundamental_analysis.py 600519.SH -n 6

  单只股票 (保存TXT报告):
    python fundamental_analysis.py 600519.SH --save-txt

  批量分析 (默认4个季度):
    python fundamental_analysis.py -f stock_pool.txt

  批量分析 (指定8个季度，使用8个进程，保存TXT):
    python fundamental_analysis.py -f stock_pool.txt -n 8 -w 8 --save-txt
        '''
    )
    parser.add_argument('stock_code', nargs='?', help='股票代码，如 600519.SH')
    parser.add_argument('-f', '--file', help='股票池文件路径')
    parser.add_argument('-n', '--num-quarters', type=int, default=4,
                       help='获取的季度数量 (默认: 4，建议范围: 4-8)')
    parser.add_argument('-w', '--workers', type=int, default=4,
                       help='批量处理时的最大进程数 (默认: 4)')
    parser.add_argument('--save-txt', action='store_true',
                       help='保存TXT详细报告 (默认: 不保存，仅保存PNG图表)')

    args = parser.parse_args()

    # 验证季度数量
    if args.num_quarters < 1:
        logger.error("季度数量必须大于0")
        sys.exit(1)

    if args.num_quarters > 20:
        logger.warning(f"季度数量 {args.num_quarters} 较大，可能影响性能")

    # 检查输入
    if not args.stock_code and not args.file:
        parser.print_help()
        sys.exit(1)

    # 单只股票分析
    if args.stock_code:
        analyze_single_stock(args.stock_code, num_quarters=args.num_quarters, save_txt=args.save_txt)

    # 批量分析
    elif args.file:
        stock_list = read_stock_pool(args.file)
        if stock_list:
            batch_analyze(stock_list, max_workers=args.workers, num_quarters=args.num_quarters, save_txt=args.save_txt)
        else:
            logger.error("股票池为空，退出")
            sys.exit(1)


if __name__ == '__main__':
    main()
