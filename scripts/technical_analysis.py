#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标分析工具
结合K线形态、成交量、MFI和OBV进行综合分析
"""

import pandas as pd
import pandas_ta as ta
import tushare as ts
from datetime import datetime, timedelta
import logging
import argparse
import os
import sys

# ==================== 路径配置 ====================
# 将项目根目录添加到 Python 路径，以便导入 database 模块
# 这样无论从哪个目录运行脚本都能正常工作
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入本地数据库查询模块
try:
    from database.query_helper import StockDataQuery
    LOCAL_DB_AVAILABLE = True
except ImportError:
    LOCAL_DB_AVAILABLE = False

# 创建输出文件夹
OUTPUT_DIR = 'technical_analysis_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """技术分析器"""

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
            # 使用在线Tushare
            # 从 token.txt 读取 Tushare token
            token_file = os.path.join(os.path.dirname(__file__), '../token.txt')
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

    def fetch_data(self, ts_code, start_date, end_date):
        """
        获取股票数据
        :param ts_code: 股票代码，如 '000001.SZ'
        :param start_date: 开始日期 'YYYYMMDD'
        :param end_date: 结束日期 'YYYYMMDD'
        :return: DataFrame
        """
        logger.info(f"获取 {ts_code} 从 {start_date} 到 {end_date} 的数据")

        if self.use_local_db:
            # 从本地数据库获取数据
            df = self.local_query.daily(ts_code, start_date, end_date)

            if df is None or df.empty:
                logger.warning(f"本地数据库中未找到 {ts_code} 的数据")
                return None

            # 按日期升序排列
            df = df.sort_values('trade_date').reset_index(drop=True)

            # 重命名列以符合 pandas-ta 的要求
            df = df.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'vol': 'Volume'
            })

            logger.info(f"从本地数据库成功获取 {len(df)} 条数据")
        else:
            # 从在线Tushare获取数据
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df.empty:
                logger.warning(f"未获取到 {ts_code} 的数据")
                return None

            # 按日期升序排列
            df = df.sort_values('trade_date').reset_index(drop=True)

            # 重命名列以符合 pandas-ta 的要求
            df = df.rename(columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'vol': 'Volume'
            })

            logger.info(f"从在线Tushare成功获取 {len(df)} 条数据")

        return df

    def calculate_indicators(self, df):
        """
        计算技术指标
        :param df: 包含 OHLCV 数据的 DataFrame
        :return: 添加了指标的 DataFrame
        """
        if df is None or df.empty:
            return None

        logger.info("计算 MFI 和 OBV 指标")

        # 计算 MFI (Money Flow Index) - 资金流量指标
        # 默认周期为14
        df['MFI'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)

        # 计算 OBV (On-Balance Volume) - 能量潮
        df['OBV'] = ta.obv(df['Close'], df['Volume'])

        # 计算 OBV 的移动平均，用于判断趋势
        df['OBV_MA'] = df['OBV'].rolling(window=20).mean()

        return df

    def identify_candle_patterns(self, df):
        """
        识别K线形态
        :param df: DataFrame
        :return: 添加了形态标识的 DataFrame
        """
        if df is None or df.empty:
            return None

        logger.info("识别K线形态")

        # 计算实体和影线长度
        df['body'] = abs(df['Close'] - df['Open'])
        df['upper_shadow'] = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['lower_shadow'] = df[['Open', 'Close']].min(axis=1) - df['Low']
        df['total_range'] = df['High'] - df['Low']

        # 避免除以零
        df['body_ratio'] = df['body'] / (df['total_range'] + 0.0001)
        df['lower_shadow_ratio'] = df['lower_shadow'] / (df['total_range'] + 0.0001)
        df['upper_shadow_ratio'] = df['upper_shadow'] / (df['total_range'] + 0.0001)

        # 识别长下影线（锤子线）
        # 条件：下影线长度 > 实体的2倍，且上影线很短
        df['is_hammer'] = (
            (df['lower_shadow'] > df['body'] * 2) &
            (df['upper_shadow'] < df['body'] * 0.3) &
            (df['body_ratio'] > 0.1)  # 实体不能太小
        )

        # 识别长上影线（射击之星）
        df['is_shooting_star'] = (
            (df['upper_shadow'] > df['body'] * 2) &
            (df['lower_shadow'] < df['body'] * 0.3) &
            (df['body_ratio'] > 0.1)
        )

        # 识别十字星（实体很小）
        df['is_doji'] = df['body_ratio'] < 0.1

        # 计算日涨跌幅（相对前一日收盘价）
        df['pct_change'] = df['Close'].pct_change() * 100

        # 识别大阳线（涨幅大且实体大）
        df['is_big_bullish'] = (
            (df['Close'] > df['Open']) &
            (df['body_ratio'] > 0.7) &
            (df['pct_change'] > 3)
        )

        # 识别大阴线
        df['is_big_bearish'] = (
            (df['Close'] < df['Open']) &
            (df['body_ratio'] > 0.7) &
            (df['pct_change'] < -3)
        )

        return df

    def analyze_volume(self, df):
        """
        分析成交量
        :param df: DataFrame
        :return: 添加了成交量分析的 DataFrame
        """
        if df is None or df.empty:
            return None

        logger.info("分析成交量")

        # 计算成交量移动平均
        df['volume_ma5'] = df['Volume'].rolling(window=5).mean()
        df['volume_ma10'] = df['Volume'].rolling(window=10).mean()

        # 计算成交量比率
        df['volume_ratio'] = df['Volume'] / (df['volume_ma5'] + 0.0001)

        # 判断是否放量（成交量 > 5日均量的1.5倍）
        df['is_volume_surge'] = df['volume_ratio'] > 1.5

        # 判断是否缩量
        df['is_volume_shrink'] = df['volume_ratio'] < 0.7

        return df

    def generate_signals(self, df):
        """
        生成交易信号
        :param df: DataFrame
        :return: 添加了信号的 DataFrame
        """
        if df is None or df.empty:
            return None

        logger.info("生成交易信号")

        # 初始化信号列
        df['signal'] = ''
        df['signal_strength'] = 0

        for i in range(20, len(df)):  # 从第20行开始，确保有足够的历史数据
            signals = []
            strength = 0

            # 1. 锤子线 + 放量 + MFI超卖 = 强烈买入信号
            if (df.loc[i, 'is_hammer'] and
                df.loc[i, 'is_volume_surge'] and
                df.loc[i, 'MFI'] < 30):
                signals.append('锤子线+放量+MFI超卖')
                strength += 3

            # 2. OBV上升 + 价格上升 = 买入信号
            if (df.loc[i, 'OBV'] > df.loc[i, 'OBV_MA'] and
                df.loc[i, 'Close'] > df.loc[i-1, 'Close']):
                signals.append('OBV上升趋势')
                strength += 2

            # 3. 大阳线 + 放量 + MFI未超买 = 买入信号
            if (df.loc[i, 'is_big_bullish'] and
                df.loc[i, 'is_volume_surge'] and
                df.loc[i, 'MFI'] < 70):
                signals.append('大阳线+放量')
                strength += 2

            # 4. 射击之星 + 放量 + MFI超买 = 卖出信号
            if (df.loc[i, 'is_shooting_star'] and
                df.loc[i, 'is_volume_surge'] and
                df.loc[i, 'MFI'] > 70):
                signals.append('射击之星+放量+MFI超买')
                strength -= 3

            # 5. OBV下降 + 价格下降 = 卖出信号
            if (df.loc[i, 'OBV'] < df.loc[i, 'OBV_MA'] and
                df.loc[i, 'Close'] < df.loc[i-1, 'Close']):
                signals.append('OBV下降趋势')
                strength -= 2

            # 6. 大阴线 + 放量 = 卖出信号
            if (df.loc[i, 'is_big_bearish'] and
                df.loc[i, 'is_volume_surge']):
                signals.append('大阴线+放量')
                strength -= 2

            # 7. MFI超买但价格滞涨 = 警示信号
            if (df.loc[i, 'MFI'] > 80 and
                df.loc[i, 'Close'] < df.loc[i-1, 'Close']):
                signals.append('MFI超买+价格滞涨')
                strength -= 1

            # 8. MFI超卖但价格企稳 = 关注信号
            if (df.loc[i, 'MFI'] < 20 and
                df.loc[i, 'Close'] > df.loc[i-1, 'Close']):
                signals.append('MFI超卖+价格企稳')
                strength += 1

            if signals:
                df.loc[i, 'signal'] = '; '.join(signals)
                df.loc[i, 'signal_strength'] = strength

        return df

    def print_analysis_report(self, df, ts_code, recent_days=10):
        """
        打印分析报告
        :param df: DataFrame
        :param ts_code: 股票代码
        :param recent_days: 显示最近N天的数据
        """
        if df is None or df.empty:
            logger.warning("无数据可分析")
            return

        print("\n" + "="*80)
        print(f"技术分析报告 - {ts_code}")
        print("="*80)

        # 显示最近的数据
        recent_df = df.tail(recent_days).copy()

        # 选择要显示的列
        display_cols = [
            'trade_date', 'Close', 'Volume', 'volume_ratio',
            'MFI', 'OBV', 'pct_change', 'signal', 'signal_strength'
        ]

        # 格式化输出
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', 50)

        print(f"\n最近 {recent_days} 天的数据:")
        print("-"*80)

        for idx, row in recent_df.iterrows():
            print(f"\n日期: {row['trade_date']}")
            print(f"  收盘价: {row['Close']:.2f}  涨跌幅: {row['pct_change']:.2f}%")
            print(f"  成交量: {row['Volume']:.0f}  量比: {row['volume_ratio']:.2f}x")
            print(f"  MFI: {row['MFI']:.2f}  OBV: {row['OBV']:.0f}")

            # K线形态
            patterns = []
            if row['is_hammer']:
                patterns.append('锤子线')
            if row['is_shooting_star']:
                patterns.append('射击之星')
            if row['is_doji']:
                patterns.append('十字星')
            if row['is_big_bullish']:
                patterns.append('大阳线')
            if row['is_big_bearish']:
                patterns.append('大阴线')

            if patterns:
                print(f"  K线形态: {', '.join(patterns)}")

            # 成交量特征
            if row['is_volume_surge']:
                print(f"  成交量: 放量")
            elif row['is_volume_shrink']:
                print(f"  成交量: 缩量")

            # 信号
            if row['signal']:
                strength_desc = "强烈" if abs(row['signal_strength']) >= 3 else "一般"
                signal_type = "买入" if row['signal_strength'] > 0 else "卖出"
                print(f"  信号: [{strength_desc}{signal_type}] {row['signal']}")

        # 统计信息
        print("\n" + "="*80)
        print("统计信息:")
        print("-"*80)

        # MFI 区间统计
        mfi_latest = recent_df['MFI'].iloc[-1]
        if mfi_latest > 80:
            mfi_status = "严重超买"
        elif mfi_latest > 70:
            mfi_status = "超买"
        elif mfi_latest < 20:
            mfi_status = "严重超卖"
        elif mfi_latest < 30:
            mfi_status = "超卖"
        else:
            mfi_status = "正常"

        print(f"MFI 当前值: {mfi_latest:.2f} - {mfi_status}")

        # OBV 趋势
        obv_trend = "上升" if recent_df['OBV'].iloc[-1] > recent_df['OBV_MA'].iloc[-1] else "下降"
        print(f"OBV 趋势: {obv_trend}")

        # 最近的强信号
        strong_signals = recent_df[abs(recent_df['signal_strength']) >= 2]
        if not strong_signals.empty:
            print(f"\n最近的强信号 ({len(strong_signals)} 个):")
            for idx, row in strong_signals.iterrows():
                signal_type = "买入" if row['signal_strength'] > 0 else "卖出"
                print(f"  {row['trade_date']}: [{signal_type}] {row['signal']}")

        print("\n" + "="*80)

    def save_to_csv(self, df, filename):
        """
        保存分析结果到CSV
        :param df: DataFrame
        :param filename: 文件名
        """
        if df is None or df.empty:
            return

        df.to_csv(filename, index=False, encoding='utf-8-sig')
        logger.info(f"分析结果已保存到 {filename}")

    def save_kline_data(self, df, filename):
        """
        保存K线基础数据，用于后续绘制K线图
        包含：日期、开盘价、最高价、最低价、收盘价、成交量
        :param df: DataFrame
        :param filename: 文件名
        """
        if df is None or df.empty:
            return

        # 选择K线图需要的基础字段
        kline_columns = ['trade_date', 'Open', 'High', 'Low', 'Close', 'Volume']

        # 检查所需列是否存在
        missing_cols = [col for col in kline_columns if col not in df.columns]
        if missing_cols:
            logger.warning(f"缺少K线数据列: {missing_cols}")
            return

        # 保存K线数据
        kline_df = df[kline_columns].copy()

        # 重命名列为更友好的名称
        kline_df.columns = ['日期', '开盘价', '最高价', '最低价', '收盘价', '成交量']

        kline_df.to_csv(filename, index=False, encoding='utf-8-sig')
        logger.info(f"K线数据已保存到 {filename}")


class TeeOutput:
    """同时输出到控制台和文件的类"""
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, 'w', encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


def main():
    parser = argparse.ArgumentParser(description='股票技术指标分析工具')
    parser.add_argument('--code', type=str, help='股票代码，如 000001.SZ 或 000001.SZ#平安银行')
    parser.add_argument('--start', type=str, help='开始日期 YYYYMMDD，与--end配合使用')
    parser.add_argument('--end', type=str, help='结束日期 YYYYMMDD，默认今天')
    parser.add_argument('--days', type=int, help='分析最近N天的数据，默认60天（如果同时指定了--start，则优先使用--start）')
    parser.add_argument('--output', type=str, help='保存结果到CSV文件')
    parser.add_argument('--pool', type=str, help='从股票池文件读取第一个股票代码进行分析')
    parser.add_argument('--use-local-db', action='store_true', help='使用本地数据库而非在线Tushare（需要先初始化数据库）')

    args = parser.parse_args()

    # 检查是否提供了股票代码或股票池文件
    if not args.code and not args.pool:
        logger.error("请提供股票代码 (--code) 或股票池文件 (--pool)")
        parser.print_help()
        sys.exit(1)

    # 处理股票池文件
    if args.pool and not args.code:
        if os.path.exists(args.pool):
            with open(args.pool, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 跳过空行和注释行
                    if not line or line.startswith('#'):
                        continue
                    # 去除行内注释并获取股票代码
                    if '#' in line:
                        code = line.split('#')[0].strip()
                    else:
                        code = line.strip()
                    if code:
                        args.code = code
                        logger.info(f"从股票池文件读取股票代码: {args.code}")
                        break

            if not args.code:
                logger.error("股票池文件中没有有效的股票代码")
                sys.exit(1)
        else:
            logger.error(f"股票池文件 {args.pool} 不存在")
            sys.exit(1)

    # 处理带注释的股票代码
    if args.code and '#' in args.code:
        args.code = args.code.split('#')[0].strip()

    # 处理日期
    if not args.end:
        args.end = datetime.now().strftime('%Y%m%d')

    if not args.start:
        # 如果没有指定开始日期，则使用 --days 参数（默认60天）
        days_to_fetch = args.days if args.days else 60
        start_dt = datetime.now() - timedelta(days=days_to_fetch)
        args.start = start_dt.strftime('%Y%m%d')
        logger.info(f"获取最近 {days_to_fetch} 天的数据 ({args.start} 到 {args.end})")
    else:
        logger.info(f"使用指定的日期范围: {args.start} 到 {args.end}")

    # 设置输出重定向到文件
    log_filename = os.path.join(OUTPUT_DIR, f'technical_analysis_{args.code}.txt')
    tee = TeeOutput(log_filename)
    sys.stdout = tee

    # 同时设置日志到文件
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(file_handler)

    try:
        # 创建分析器
        analyzer = TechnicalAnalyzer(use_local_db=args.use_local_db)

        # 获取数据
        df = analyzer.fetch_data(args.code, args.start, args.end)

        if df is not None:
            # 计算指标
            df = analyzer.calculate_indicators(df)
            df = analyzer.identify_candle_patterns(df)
            df = analyzer.analyze_volume(df)
            df = analyzer.generate_signals(df)

            # 显示报告
            # 如果获取的数据超过30天，只显示最近30天；否则显示全部
            days_fetched = args.days if args.days else 60
            display_days = min(len(df), 100) if days_fetched > 100 else len(df)
            analyzer.print_analysis_report(df, args.code, recent_days=display_days)

            # 保存结果到输出文件夹
            if args.output:
                csv_output = os.path.join(OUTPUT_DIR, args.output)
            else:
                csv_output = os.path.join(OUTPUT_DIR, f'technical_analysis_{args.code}.csv')

            analyzer.save_to_csv(df, csv_output)

            # 保存K线基础数据（用于绘图）
            kline_output = os.path.join(OUTPUT_DIR, f'kline_data_{args.code}.csv')
            analyzer.save_kline_data(df, kline_output)

            print(f"\n所有结果已保存到文件夹: {OUTPUT_DIR}")
            print(f"  - 完整分析数据: {csv_output}")
            print(f"  - K线基础数据: {kline_output}")
            print(f"  - 分析日志: {log_filename}")

    finally:
        # 恢复标准输出
        sys.stdout = tee.terminal
        tee.close()


if __name__ == '__main__':
    main()
