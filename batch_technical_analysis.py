#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量技术指标分析工具
对pool.txt中的所有股票进行技术分析并排序
"""

import pandas as pd
import pandas_ta as ta
import tushare as ts
from datetime import datetime, timedelta
import logging
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入本地数据库查询模块
try:
    from database.query_helper import StockDataQuery
    LOCAL_DB_AVAILABLE = True
except ImportError:
    LOCAL_DB_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("本地数据库模块未安装，将使用在线Tushare数据")

# 创建输出文件夹
OUTPUT_DIR = 'batch_analysis_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class BatchTechnicalAnalyzer:
    """批量技术分析器"""

    def __init__(self, use_local_db=False):
        """
        初始化

        Args:
            use_local_db: 是否使用本地数据库，默认False（使用在线Tushare）
        """
        self.use_local_db = use_local_db and LOCAL_DB_AVAILABLE
        self.local_query = None

        if self.use_local_db:
            # 使用本地数据库
            self.local_query = StockDataQuery()
            logger.info("使用本地数据库作为数据源")
        else:
            # 使用在线Tushare，从token.txt读取token
            token_file = os.path.join(os.path.dirname(__file__), 'token.txt')
            try:
                with open(token_file, 'r', encoding='utf-8') as f:
                    ts_token = f.read().strip()
                if not ts_token:
                    raise ValueError("token.txt 文件为空")
            except FileNotFoundError:
                logger.error(f"未找到 token.txt 文件，请在 {token_file} 中添加您的 tushare token")
                raise
            except Exception as e:
                logger.error(f"读取 token.txt 文件失败: {e}")
                raise

            ts.set_token(ts_token)
            self.pro = ts.pro_api()
            logger.info("使用在线Tushare作为数据源")

        # 存储所有股票的分析结果
        self.all_results = []

        # 存储股票代码和中文名称的映射
        self.stock_names = {}

    def read_stock_pool(self, pool_file='pool.txt'):
        """
        读取股票代码池
        :param pool_file: 股票代码文件路径
        :return: 股票代码列表
        """
        if not os.path.exists(pool_file):
            logger.error(f"股票池文件 {pool_file} 不存在")
            return []

        stocks = []
        with open(pool_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释行
                if not line or line.startswith('#'):
                    continue
                # 提取股票代码和中文名称
                if '#' in line:
                    parts = line.split('#')
                    code = parts[0].strip()
                    name = parts[1].strip() if len(parts) > 1 else ''
                    # 保存代码和名称的映射
                    if code:
                        self.stock_names[code] = name
                else:
                    code = line.strip()
                    if code:
                        self.stock_names[code] = ''
                # 确保代码不为空
                if code:
                    stocks.append(code)

        logger.info(f"从 {pool_file} 读取到 {len(stocks)} 只股票")
        return stocks

    def format_stock_code(self, ts_code):
        """
        格式化股票代码，附加中文名称
        :param ts_code: 股票代码
        :return: 格式化的字符串 "代码 中文名"
        """
        name = self.stock_names.get(ts_code, '')
        if name:
            return f"{ts_code} {name}"
        return ts_code

    def batch_fetch_data(self, stock_codes, start_date, end_date):
        """
        批量获取股票数据
        :param stock_codes: 股票代码列表
        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: 包含所有股票数据的字典
        """
        all_data = {}

        logger.info(f"开始批量获取 {len(stock_codes)} 只股票的数据")
        logger.info(f"日期范围: {start_date} 到 {end_date}")

        # 使用本地数据库
        if self.use_local_db:
            for i, code in enumerate(stock_codes, 1):
                try:
                    df = self.local_query.daily(code, start_date, end_date)
                    if df is not None and not df.empty:
                        # 按日期升序排列
                        df = df.sort_values('trade_date').reset_index(drop=True)

                        # 重命名列
                        df = df.rename(columns={
                            'open': 'Open',
                            'high': 'High',
                            'low': 'Low',
                            'close': 'Close',
                            'vol': 'Volume'
                        })

                        all_data[code] = df
                        logger.info(f"  [{i}/{len(stock_codes)}] {self.format_stock_code(code)}: 从本地数据库获取到 {len(df)} 条数据")
                    else:
                        logger.warning(f"  [{i}/{len(stock_codes)}] {self.format_stock_code(code)}: 本地数据库无数据")
                except Exception as e:
                    logger.error(f"  [{i}/{len(stock_codes)}] {self.format_stock_code(code)}: 获取失败 - {e}")

            logger.info(f"从本地数据库成功获取 {len(all_data)} 只股票的数据")
            return all_data

        # 使用在线Tushare（原有逻辑）
        batch_size = 50  # 每批次处理50只股票（tushare限制）

        # 分批处理股票
        for i in range(0, len(stock_codes), batch_size):
            batch_codes = stock_codes[i:i+batch_size]
            codes_str = ','.join(batch_codes)

            try:
                logger.info(f"获取第 {i//batch_size + 1} 批次数据 ({len(batch_codes)} 只股票)")

                # 批量获取数据
                df = self.pro.daily(
                    ts_code=codes_str,
                    start_date=start_date,
                    end_date=end_date
                )

                if not df.empty:
                    # 按股票代码分组
                    for code in batch_codes:
                        stock_df = df[df['ts_code'] == code].copy()
                        if not stock_df.empty:
                            # 按日期升序排列
                            stock_df = stock_df.sort_values('trade_date').reset_index(drop=True)

                            # 重命名列
                            stock_df = stock_df.rename(columns={
                                'open': 'Open',
                                'high': 'High',
                                'low': 'Low',
                                'close': 'Close',
                                'vol': 'Volume'
                            })

                            all_data[code] = stock_df
                            logger.info(f"  {self.format_stock_code(code)}: 获取到 {len(stock_df)} 条数据")
                        else:
                            logger.warning(f"  {self.format_stock_code(code)}: 无数据")

                # 避免触发API频率限制
                time.sleep(0.2)  # 每批次间隔0.2秒

            except Exception as e:
                logger.error(f"批次 {i//batch_size + 1} 获取失败: {e}")
                # 如果批量失败，改为单个获取
                for code in batch_codes:
                    try:
                        df = self.pro.daily(
                            ts_code=code,
                            start_date=start_date,
                            end_date=end_date
                        )
                        if not df.empty:
                            df = df.sort_values('trade_date').reset_index(drop=True)
                            df = df.rename(columns={
                                'open': 'Open',
                                'high': 'High',
                                'low': 'Low',
                                'close': 'Close',
                                'vol': 'Volume'
                            })
                            all_data[code] = df
                            logger.info(f"  {self.format_stock_code(code)}: 单独获取到 {len(df)} 条数据")
                        time.sleep(0.1)  # API调用间隔
                    except Exception as e2:
                        logger.error(f"  {self.format_stock_code(code)}: 单独获取失败 - {e2}")

        logger.info(f"成功获取 {len(all_data)} 只股票的数据")
        return all_data

    def analyze_stock(self, ts_code, df):
        """
        分析单只股票
        :param ts_code: 股票代码
        :param df: 股票数据DataFrame
        :return: 分析结果字典
        """
        if df is None or df.empty:
            return None

        try:
            # 计算MFI和OBV
            df['MFI'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
            df['OBV'] = ta.obv(df['Close'], df['Volume'])
            df['OBV_MA'] = df['OBV'].rolling(window=20).mean()

            # 计算涨跌幅
            df['pct_change'] = df['Close'].pct_change() * 100

            # 计算成交量指标
            df['volume_ma5'] = df['Volume'].rolling(window=5).mean()
            df['volume_ratio'] = df['Volume'] / (df['volume_ma5'] + 0.0001)

            # 计算移动平均线
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA10'] = df['Close'].rolling(window=10).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()

            # 识别K线形态
            df['body'] = abs(df['Close'] - df['Open'])
            df['upper_shadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
            df['lower_shadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']
            df['total_range'] = df['High'] - df['Low']

            # 获取最新数据
            latest = df.iloc[-1]

            # 计算技术指标得分
            score = 0
            signals = []

            # MFI评分
            if latest['MFI'] < 20:
                score += 3
                signals.append('MFI严重超卖')
            elif latest['MFI'] < 30:
                score += 2
                signals.append('MFI超卖')
            elif latest['MFI'] > 80:
                score -= 3
                signals.append('MFI严重超买')
            elif latest['MFI'] > 70:
                score -= 2
                signals.append('MFI超买')

            # OBV趋势评分
            if latest['OBV'] > latest['OBV_MA']:
                score += 2
                signals.append('OBV上升趋势')
            else:
                score -= 2
                signals.append('OBV下降趋势')

            # 成交量评分
            if latest['volume_ratio'] > 1.5:
                if latest['pct_change'] > 0:
                    score += 2
                    signals.append('放量上涨')
                else:
                    score -= 2
                    signals.append('放量下跌')

            # 均线评分
            if latest['Close'] > latest['MA5'] > latest['MA10'] > latest['MA20']:
                score += 3
                signals.append('多头排列')
            elif latest['Close'] < latest['MA5'] < latest['MA10'] < latest['MA20']:
                score -= 3
                signals.append('空头排列')

            # 计算5日、10日涨跌幅
            pct_5d = (latest['Close'] / df.iloc[-5]['Close'] - 1) * 100 if len(df) >= 5 else 0
            pct_10d = (latest['Close'] / df.iloc[-10]['Close'] - 1) * 100 if len(df) >= 10 else 0

            # 返回分析结果
            result = {
                'ts_code': ts_code,
                'latest_date': latest['trade_date'],
                'close': latest['Close'],
                'pct_change': latest['pct_change'],
                'pct_5d': pct_5d,
                'pct_10d': pct_10d,
                'volume': latest['Volume'],
                'volume_ratio': latest['volume_ratio'],
                'mfi': latest['MFI'],
                'obv_trend': 'UP' if latest['OBV'] > latest['OBV_MA'] else 'DOWN',
                'score': score,
                'signals': '; '.join(signals),
                'ma5': latest['MA5'],
                'ma10': latest['MA10'],
                'ma20': latest['MA20']
            }

            return result

        except Exception as e:
            logger.error(f"分析 {ts_code} 时出错: {e}")
            return None

    def batch_analyze(self, stock_data):
        """
        批量分析所有股票
        :param stock_data: 股票数据字典
        :return: 分析结果列表
        """
        results = []

        logger.info(f"开始分析 {len(stock_data)} 只股票")

        for ts_code, df in stock_data.items():
            result = self.analyze_stock(ts_code, df)
            if result:
                results.append(result)
                logger.info(f"  {self.format_stock_code(ts_code)}: 分析完成，得分 {result['score']}")

        return results

    def sort_and_rank_results(self, results, sort_by='score'):
        """
        对分析结果进行排序和排名
        :param results: 分析结果列表
        :param sort_by: 排序依据
        :return: 排序后的DataFrame
        """
        if not results:
            return pd.DataFrame()

        # 转换为DataFrame
        df = pd.DataFrame(results)

        # 根据不同指标排序
        if sort_by == 'score':
            df = df.sort_values('score', ascending=False)
        elif sort_by == 'mfi':
            df = df.sort_values('mfi', ascending=True)  # MFI越低越超卖
        elif sort_by == 'pct_5d':
            df = df.sort_values('pct_5d', ascending=False)
        elif sort_by == 'pct_10d':
            df = df.sort_values('pct_10d', ascending=False)
        elif sort_by == 'volume_ratio':
            df = df.sort_values('volume_ratio', ascending=False)

        # 添加排名
        df['rank'] = range(1, len(df) + 1)

        return df

    def generate_comprehensive_report(self, results_df, output_file=None):
        """
        生成综合分析报告
        :param results_df: 分析结果DataFrame
        :param output_file: 输出文件名
        """
        if results_df.empty:
            logger.warning("没有分析结果可生成报告")
            return

        report_lines = []
        report_lines.append("\n" + "="*100)
        report_lines.append("批量技术分析综合报告")
        report_lines.append("="*100)
        report_lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"分析股票数量: {len(results_df)}")
        report_lines.append("\n")

        # 1. 综合得分排行榜
        report_lines.append("-"*100)
        report_lines.append("【综合得分排行榜 TOP 20】")
        report_lines.append("-"*100)

        top_score = results_df.nlargest(20, 'score')
        for idx, row in top_score.iterrows():
            report_lines.append(f"{row['rank']:3d}. {self.format_stock_code(row['ts_code']):20s} | 得分: {row['score']:+3.0f} | "
                              f"收盘: {row['close']:7.2f} | 日涨跌: {row['pct_change']:+6.2f}% | "
                              f"MFI: {row['mfi']:5.1f} | {row['signals']}")

        # 2. MFI超卖股票（MFI < 30）
        report_lines.append("\n" + "-"*100)
        report_lines.append("【MFI超卖股票】(MFI < 30)")
        report_lines.append("-"*100)

        oversold = results_df[results_df['mfi'] < 30].sort_values('mfi')
        if not oversold.empty:
            for idx, row in oversold.iterrows():
                report_lines.append(f"{self.format_stock_code(row['ts_code']):20s} | MFI: {row['mfi']:5.1f} | "
                                  f"收盘: {row['close']:7.2f} | 5日涨跌: {row['pct_5d']:+6.2f}% | "
                                  f"得分: {row['score']:+3.0f}")
        else:
            report_lines.append("无超卖股票")

        # 3. MFI超买股票（MFI > 70）
        report_lines.append("\n" + "-"*100)
        report_lines.append("【MFI超买股票】(MFI > 70)")
        report_lines.append("-"*100)

        overbought = results_df[results_df['mfi'] > 70].sort_values('mfi', ascending=False)
        if not overbought.empty:
            for idx, row in overbought.iterrows():
                report_lines.append(f"{self.format_stock_code(row['ts_code']):20s} | MFI: {row['mfi']:5.1f} | "
                                  f"收盘: {row['close']:7.2f} | 5日涨跌: {row['pct_5d']:+6.2f}% | "
                                  f"得分: {row['score']:+3.0f}")
        else:
            report_lines.append("无超买股票")

        # 4. 放量股票（量比 > 1.5）
        report_lines.append("\n" + "-"*100)
        report_lines.append("【放量股票】(量比 > 1.5)")
        report_lines.append("-"*100)

        high_volume = results_df[results_df['volume_ratio'] > 1.5].sort_values('volume_ratio', ascending=False)
        if not high_volume.empty:
            for idx, row in high_volume.head(10).iterrows():
                report_lines.append(f"{self.format_stock_code(row['ts_code']):20s} | 量比: {row['volume_ratio']:5.2f}x | "
                                  f"日涨跌: {row['pct_change']:+6.2f}% | 成交量: {row['volume']:,.0f}")
        else:
            report_lines.append("无明显放量股票")

        # 5. 5日涨幅排行
        report_lines.append("\n" + "-"*100)
        report_lines.append("【5日涨幅排行 TOP 10】")
        report_lines.append("-"*100)

        top_5d = results_df.nlargest(10, 'pct_5d')
        for idx, row in top_5d.iterrows():
            report_lines.append(f"{self.format_stock_code(row['ts_code']):20s} | 5日涨幅: {row['pct_5d']:+7.2f}% | "
                              f"10日涨幅: {row['pct_10d']:+7.2f}% | MFI: {row['mfi']:5.1f}")

        # 6. OBV趋势统计
        report_lines.append("\n" + "-"*100)
        report_lines.append("【OBV趋势统计】")
        report_lines.append("-"*100)

        obv_up = len(results_df[results_df['obv_trend'] == 'UP'])
        obv_down = len(results_df[results_df['obv_trend'] == 'DOWN'])
        report_lines.append(f"上升趋势: {obv_up} 只 ({obv_up/len(results_df)*100:.1f}%)")
        report_lines.append(f"下降趋势: {obv_down} 只 ({obv_down/len(results_df)*100:.1f}%)")

        # 7. 综合建议
        report_lines.append("\n" + "-"*100)
        report_lines.append("【综合建议】")
        report_lines.append("-"*100)

        strong_buy = results_df[results_df['score'] >= 5]
        if not strong_buy.empty:
            formatted_codes = [self.format_stock_code(code) for code in strong_buy['ts_code'].tolist()]
            report_lines.append(f"强烈关注（得分≥5）: {', '.join(formatted_codes)}")

        moderate_buy = results_df[(results_df['score'] >= 3) & (results_df['score'] < 5)]
        if not moderate_buy.empty:
            formatted_codes = [self.format_stock_code(code) for code in moderate_buy['ts_code'].tolist()[:10]]
            report_lines.append(f"适度关注（3≤得分<5）: {', '.join(formatted_codes)}")

        warning = results_df[results_df['score'] <= -3]
        if not warning.empty:
            formatted_codes = [self.format_stock_code(code) for code in warning['ts_code'].tolist()]
            report_lines.append(f"风险警示（得分≤-3）: {', '.join(formatted_codes)}")

        report_lines.append("\n" + "="*100)

        # 打印报告
        report_text = '\n'.join(report_lines)
        print(report_text)

        # 保存报告
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            logger.info(f"报告已保存到 {output_file}")

        return report_text

    def save_all_results(self, results_df, filename):
        """
        保存所有分析结果到CSV
        :param results_df: 分析结果DataFrame
        :param filename: 文件名
        """
        if results_df.empty:
            return

        # 重新排列列的顺序
        columns_order = [
            'rank', 'ts_code', 'latest_date', 'score',
            'close', 'pct_change', 'pct_5d', 'pct_10d',
            'mfi', 'obv_trend', 'volume_ratio',
            'ma5', 'ma10', 'ma20', 'signals'
        ]

        results_df = results_df[columns_order]

        # 保存到CSV
        results_df.to_csv(filename, index=False, encoding='utf-8-sig')
        logger.info(f"所有分析结果已保存到 {filename}")


def create_sample_pool_file():
    """创建示例股票池文件"""
    sample_stocks = [
        "000001.SZ",  # 平安银行
        "000002.SZ",  # 万科A
        "000858.SZ",  # 五粮液
        "002415.SZ",  # 海康威视
        "300750.SZ",  # 宁德时代
        "600036.SH",  # 招商银行
        "600519.SH",  # 贵州茅台
        "000333.SZ",  # 美的集团
        "002594.SZ",  # 比亚迪
        "300059.SZ",  # 东方财富
    ]

    with open('pool.txt', 'w', encoding='utf-8') as f:
        f.write("# 股票代码池\n")
        f.write("# 格式: 股票代码.交易所 (如 000001.SZ)\n")
        f.write("# 以#开头的行为注释\n\n")
        for stock in sample_stocks:
            f.write(f"{stock}\n")

    logger.info("已创建示例股票池文件 pool.txt")


def main():
    parser = argparse.ArgumentParser(description='批量股票技术指标分析工具')
    parser.add_argument('--pool', type=str, default='pool.txt', help='股票池文件路径，默认pool.txt')
    parser.add_argument('--start', type=str, help='开始日期 YYYYMMDD，默认60天前')
    parser.add_argument('--end', type=str, help='结束日期 YYYYMMDD，默认今天')
    parser.add_argument('--sort', type=str, default='score',
                       choices=['score', 'mfi', 'pct_5d', 'pct_10d', 'volume_ratio'],
                       help='排序依据，默认按综合得分排序')
    parser.add_argument('--create-sample', action='store_true', help='创建示例股票池文件')
    parser.add_argument('--use-local-db', action='store_true', help='使用本地数据库而非在线Tushare（需要先初始化数据库）')

    args = parser.parse_args()

    # 创建示例文件
    if args.create_sample:
        create_sample_pool_file()
        return

    # 处理日期
    if not args.end:
        args.end = datetime.now().strftime('%Y%m%d')
    if not args.start:
        start_dt = datetime.now() - timedelta(days=60)
        args.start = start_dt.strftime('%Y%m%d')

    # 创建分析器
    analyzer = BatchTechnicalAnalyzer(use_local_db=args.use_local_db)

    # 读取股票池
    stock_codes = analyzer.read_stock_pool(args.pool)
    if not stock_codes:
        logger.error("未读取到股票代码，请检查股票池文件")
        logger.info("可以使用 --create-sample 参数创建示例股票池文件")
        return

    # 批量获取数据
    stock_data = analyzer.batch_fetch_data(stock_codes, args.start, args.end)

    if not stock_data:
        logger.error("未获取到任何股票数据")
        return

    # 批量分析
    results = analyzer.batch_analyze(stock_data)

    if not results:
        logger.error("分析失败，未生成任何结果")
        return

    # 排序和排名
    results_df = analyzer.sort_and_rank_results(results, sort_by=args.sort)

    # 生成文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 保存详细结果
    csv_filename = os.path.join(OUTPUT_DIR, f'batch_analysis_{timestamp}.csv')
    analyzer.save_all_results(results_df, csv_filename)

    # 生成并保存综合报告
    report_filename = os.path.join(OUTPUT_DIR, f'batch_report_{timestamp}.txt')
    analyzer.generate_comprehensive_report(results_df, report_filename)

    # 打印总结
    print(f"\n批量分析完成！")
    print(f"分析股票数: {len(results)}")
    print(f"详细结果: {csv_filename}")
    print(f"综合报告: {report_filename}")

    # 显示得分最高的5只股票
    print(f"\n得分最高的5只股票:")
    top5 = results_df.head(5)
    for idx, row in top5.iterrows():
        print(f"  {row['rank']}. {analyzer.format_stock_code(row['ts_code'])} - 得分: {row['score']:+.0f}, MFI: {row['mfi']:.1f}")


if __name__ == '__main__':
    main()