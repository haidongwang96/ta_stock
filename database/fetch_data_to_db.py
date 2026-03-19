"""
从Tushare获取股票数据并存入本地数据库
支持全量初始化和增量更新
"""

import os
import sys
import argparse
import time
from datetime import datetime, timedelta
import pandas as pd
import tushare as ts
import pandas_ta as ta
import logging
from typing import List, Optional

# 添加父目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from database.db_manager import DAILY_BASIC_FIELDS, StockDatabase

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DAILY_BASIC_FETCH_FIELDS = ['ts_code', 'trade_date', *DAILY_BASIC_FIELDS]


class DataFetcher:
    """数据抓取和处理类"""

    def __init__(self, db_path: str = None):
        """
        初始化数据抓取器

        Args:
            db_path: 数据库文件路径
        """
        # 读取Tushare token
        token_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'token.txt'
        )

        if not os.path.exists(token_file):
            raise FileNotFoundError("未找到token.txt文件，请先创建并填入Tushare token")

        with open(token_file, 'r', encoding='utf-8') as f:
            ts_token = f.read().strip()

        ts.set_token(ts_token)
        self.pro = ts.pro_api()

        # 初始化数据库
        self.db = StockDatabase(db_path)

        # 交易日历缓存
        self.trade_cal_cache = {}

        logger.info("数据抓取器初始化完成")

    def is_trade_date(self, date: str) -> bool:
        """
        判断指定日期是否为股票交易日

        Args:
            date: 日期字符串，格式为 YYYYMMDD

        Returns:
            True表示是交易日，False表示非交易日
        """
        try:
            # 获取年份用于缓存
            year = date[:4]

            # 如果该年份的交易日历未缓存，则获取
            if year not in self.trade_cal_cache:
                start_date = f"{year}0101"
                end_date = f"{year}1231"

                logger.debug(f"获取{year}年交易日历...")
                df = self.pro.trade_cal(
                    exchange='SSE',  # 上交所
                    start_date=start_date,
                    end_date=end_date,
                    fields='cal_date,is_open'
                )

                if df is not None and not df.empty:
                    # 将交易日存入缓存（字典：日期 -> 是否开市）
                    self.trade_cal_cache[year] = dict(
                        zip(df['cal_date'], df['is_open'])
                    )
                    logger.debug(f"{year}年交易日历已缓存，共{len(df)}天")
                else:
                    logger.warning(f"获取{year}年交易日历失败")
                    return True  # 获取失败时默认返回True，继续执行

            # 从缓存中查询
            if year in self.trade_cal_cache:
                is_open = self.trade_cal_cache[year].get(date, 0)
                return bool(is_open == 1)
            else:
                # 缓存中没有，默认返回True
                return True

        except Exception as e:
            logger.warning(f"判断交易日失败: {e}，默认视为交易日")
            return True

    def fetch_stock_basic(self):
        """
        获取并更新股票基本信息
        """
        logger.info("开始获取股票基本信息...")

        try:
            # 获取所有A股基本信息
            df = self.pro.stock_basic(
                exchange='',
                list_status='L',  # L=上市 D=退市 P=暂停上市
                fields='ts_code,symbol,name,area,industry,market,list_date'
            )

            if df is not None and not df.empty:
                self.db.insert_stock_basic(df)
                logger.info(f"✅ 成功更新 {len(df)} 只股票的基本信息")
            else:
                logger.warning("❌ 未获取到股票基本信息")

        except Exception as e:
            logger.error(f"❌ 获取股票基本信息失败: {e}")

    def fetch_daily_data(self, ts_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        从Tushare获取日线数据，并合并 daily_basic 扩展字段

        Args:
            ts_code: 股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            包含日线数据及 daily_basic 扩展字段的DataFrame
        """
        try:
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is None or df.empty:
                logger.warning(f"{ts_code} 在 {start_date} 至 {end_date} 期间无数据")
                return None

            # 按日期排序
            df = df.sort_values('trade_date', ascending=True).reset_index(drop=True)

            # 获取 daily_basic 扩展字段并合并
            try:
                daily_basic = self.pro.daily_basic(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields=",".join(DAILY_BASIC_FETCH_FIELDS),
                )
                if daily_basic is not None and not daily_basic.empty:
                    df = pd.merge(
                        df,
                        daily_basic[DAILY_BASIC_FETCH_FIELDS],
                        on=['ts_code', 'trade_date'],
                        how='left',
                    )
                else:
                    for field in DAILY_BASIC_FIELDS:
                        df[field] = None
            except Exception as e:
                logger.warning(f"获取 {ts_code} daily_basic 扩展字段失败，置为 null: {e}")
                for field in DAILY_BASIC_FIELDS:
                    df[field] = None

            return df

        except Exception as e:
            logger.error(f"❌ 获取 {ts_code} 日线数据失败: {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标

        Args:
            df: 包含OHLCV数据的DataFrame

        Returns:
            包含技术指标的DataFrame
        """
        if df is None or df.empty or len(df) < 20:
            logger.warning("数据不足，无法计算技术指标")
            return pd.DataFrame()

        # 创建副本避免修改原数据
        df_calc = df.copy()

        # 转换日期格式为datetime（用于VWAP计算）
        if 'trade_date' in df_calc.columns:
            df_calc['trade_date'] = pd.to_datetime(df_calc['trade_date'], format='%Y%m%d')

        # 重命名字段以适配pandas_ta
        df_calc.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'vol': 'Volume'
        }, inplace=True)

        try:
            # 1. 均线指标
            df_calc['ma5'] = ta.sma(df_calc['Close'], length=5)
            df_calc['ma10'] = ta.sma(df_calc['Close'], length=10)
            df_calc['ma20'] = ta.sma(df_calc['Close'], length=20)
            if len(df_calc) >= 60:
                df_calc['ma60'] = ta.sma(df_calc['Close'], length=60)

            # 2. MACD指标
            macd = ta.macd(df_calc['Close'], fast=12, slow=26, signal=9)
            if macd is not None and not macd.empty:
                # 查找MACD相关列（兼容不同版本）
                macd_col = next((col for col in macd.columns if col.startswith('MACD_') and not col.startswith('MACDh_') and not col.startswith('MACDs_')), None)
                macds_col = next((col for col in macd.columns if col.startswith('MACDs_')), None)
                macdh_col = next((col for col in macd.columns if col.startswith('MACDh_')), None)

                if macd_col and macds_col and macdh_col:
                    df_calc['macd_dif'] = macd[macd_col]
                    df_calc['macd_dea'] = macd[macds_col]
                    df_calc['macd_hist'] = macd[macdh_col]
                else:
                    df_calc['macd_dif'] = None
                    df_calc['macd_dea'] = None
                    df_calc['macd_hist'] = None

            # 3. RSI指标
            df_calc['rsi'] = ta.rsi(df_calc['Close'], length=14)

            # 4. KDJ指标
            stoch = ta.stoch(df_calc['High'], df_calc['Low'], df_calc['Close'],
                           k=9, d=3, smooth_k=3)
            if stoch is not None and not stoch.empty:
                # 查找STOCH相关列（兼容不同版本）
                stochk_col = next((col for col in stoch.columns if col.startswith('STOCHk_')), None)
                stochd_col = next((col for col in stoch.columns if col.startswith('STOCHd_')), None)

                if stochk_col and stochd_col:
                    df_calc['kdj_k'] = stoch[stochk_col]
                    df_calc['kdj_d'] = stoch[stochd_col]
                    # J = 3K - 2D
                    df_calc['kdj_j'] = 3 * df_calc['kdj_k'] - 2 * df_calc['kdj_d']
                else:
                    df_calc['kdj_k'] = None
                    df_calc['kdj_d'] = None
                    df_calc['kdj_j'] = None

            # 5. CCI指标
            df_calc['cci'] = ta.cci(df_calc['High'], df_calc['Low'], df_calc['Close'], length=14)

            # 6. 布林带
            bbands = ta.bbands(df_calc['Close'], length=20, std=2)
            if bbands is not None and not bbands.empty:
                # 兼容不同版本的pandas_ta列名
                # 旧版本: BBU_20_2.0, BBM_20_2.0, BBL_20_2.0
                # 新版本: BBU_20_2.0_2.0, BBM_20_2.0_2.0, BBL_20_2.0_2.0
                upper_col = None
                mid_col = None
                lower_col = None

                for col in bbands.columns:
                    if col.startswith('BBU_'):
                        upper_col = col
                    elif col.startswith('BBM_'):
                        mid_col = col
                    elif col.startswith('BBL_'):
                        lower_col = col

                if upper_col and mid_col and lower_col:
                    df_calc['boll_upper'] = bbands[upper_col]
                    df_calc['boll_mid'] = bbands[mid_col]
                    df_calc['boll_lower'] = bbands[lower_col]
                    # 布林带宽度
                    df_calc['boll_width'] = (df_calc['boll_upper'] - df_calc['boll_lower']) / df_calc['boll_mid']
                else:
                    logger.debug(f"布林带列名不匹配，实际列名: {bbands.columns.tolist()}")
                    df_calc['boll_upper'] = None
                    df_calc['boll_mid'] = None
                    df_calc['boll_lower'] = None
                    df_calc['boll_width'] = None

            # 7. ATR指标
            df_calc['atr'] = ta.atr(df_calc['High'], df_calc['Low'], df_calc['Close'], length=14)

            # 8. OBV指标
            df_calc['obv'] = ta.obv(df_calc['Close'], df_calc['Volume'])

            # 9. MFI指标
            df_calc['mfi'] = ta.mfi(df_calc['High'], df_calc['Low'],
                                   df_calc['Close'], df_calc['Volume'], length=14)

            # 10. VWAP指标 - 需要 DatetimeIndex
            # 临时设置 trade_date 为索引以满足 VWAP 计算要求
            if 'trade_date' in df_calc.columns:
                df_temp = df_calc.set_index('trade_date', drop=False)
                try:
                    df_temp['vwap'] = ta.vwap(df_temp['High'], df_temp['Low'],
                                             df_temp['Close'], df_temp['Volume'])
                    df_calc['vwap'] = df_temp['vwap'].values
                except Exception as e:
                    logger.debug(f"VWAP计算失败: {e}")
                    df_calc['vwap'] = None
            else:
                df_calc['vwap'] = None

            # 11. 量比（5日平均成交量比）
            vol_ma5 = ta.sma(df_calc['Volume'], length=5)
            df_calc['vol_ratio'] = df_calc['Volume'] / vol_ma5

            # 11.5. VSA量价分析指标
            # 成交量均线（20日）
            df_calc['vma20'] = ta.sma(df_calc['Volume'], length=20)
            # 成交量倍数（当前成交量相对VMA20）
            df_calc['volume_multiple'] = df_calc['Volume'] / df_calc['vma20']
            # 避免除零错误
            df_calc['volume_multiple'] = df_calc['volume_multiple'].replace([float('inf'), -float('inf')], None)

            # 12. SAR指标
            sar = ta.psar(df_calc['High'], df_calc['Low'], df_calc['Close'])
            if sar is not None and not sar.empty:
                # 查找PSAR相关列（兼容不同版本）
                psarl_col = next((col for col in sar.columns if col.startswith('PSARl_')), None)
                psars_col = next((col for col in sar.columns if col.startswith('PSARs_')), None)

                if psarl_col and psars_col:
                    df_calc['sar'] = sar[psarl_col]  # 长仓SAR
                    # 如果长仓SAR为NaN，使用短仓SAR
                    sar_short = sar[psars_col]
                    df_calc['sar'] = df_calc['sar'].fillna(sar_short)
                else:
                    df_calc['sar'] = None

            # 准备返回的指标数据
            indicator_columns = [
                'ts_code', 'trade_date',
                'ma5', 'ma10', 'ma20', 'ma60',
                'macd_dif', 'macd_dea', 'macd_hist',
                'rsi', 'kdj_k', 'kdj_d', 'kdj_j', 'cci',
                'boll_upper', 'boll_mid', 'boll_lower', 'boll_width',
                'obv', 'mfi', 'vwap', 'vol_ratio',
                'vma20', 'volume_multiple',  # VSA量价分析指标
                'atr', 'sar'
            ]

            # 只保留存在的列
            available_columns = [col for col in indicator_columns if col in df_calc.columns]
            result_df = df_calc[available_columns].copy()

            # 将trade_date转换回字符串格式（YYYYMMDD）以便存储到数据库
            if 'trade_date' in result_df.columns:
                result_df['trade_date'] = result_df['trade_date'].dt.strftime('%Y%m%d')

            return result_df

        except Exception as e:
            logger.error(f"❌ 计算技术指标失败: {e}")
            return pd.DataFrame()

    def process_stock(self, ts_code: str, start_date: str, end_date: str,
                     replace: bool = False) -> bool:
        """
        处理单个股票的数据获取、计算和存储

        Args:
            ts_code: 股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            replace: 是否替换已存在的数据

        Returns:
            是否成功
        """
        logger.info(f"开始处理 {ts_code} ({start_date} 至 {end_date})")

        # 1. 获取日线数据
        daily_df = self.fetch_daily_data(ts_code, start_date, end_date)
        if daily_df is None or daily_df.empty:
            logger.warning(f"❌ {ts_code} 获取数据失败或无数据")
            return False

        # 2. 存储原始OHLCV数据
        self.db.insert_daily_ohlcv(daily_df, replace=replace)

        # 3. 计算技术指标
        indicators_df = self.calculate_indicators(daily_df)

        # 4. 存储技术指标
        if not indicators_df.empty:
            self.db.insert_daily_indicators(indicators_df, replace=replace)

        logger.info(f"✅ {ts_code} 数据处理完成 ({len(daily_df)} 条记录)")
        return True

    def init_database(self, stock_codes: List[str], days: int = 365):
        """
        初始化数据库（全量导入）

        Args:
            stock_codes: 股票代码列表
            days: 获取最近N天的数据
        """
        logger.info(f"开始初始化数据库，共 {len(stock_codes)} 只股票，获取最近 {days} 天数据")

        # 1. 更新股票基本信息
        self.fetch_stock_basic()

        # 2. 计算日期范围
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        # 3. 批量处理股票
        success_count = 0
        failed_stocks = []

        for i, code in enumerate(stock_codes, 1):
            try:
                logger.info(f"[{i}/{len(stock_codes)}] 处理 {code}")
                if self.process_stock(code, start_date, end_date, replace=True):
                    success_count += 1
                else:
                    failed_stocks.append(code)

                # API限流：每次请求后暂停
                time.sleep(0.15)

            except Exception as e:
                logger.error(f"❌ 处理 {code} 时发生错误: {e}")
                failed_stocks.append(code)
                continue

        # 4. 输出统计信息
        logger.info("\n" + "="*60)
        logger.info("初始化完成！")
        logger.info(f"✅ 成功: {success_count} 只")
        logger.info(f"❌ 失败: {len(failed_stocks)} 只")
        if failed_stocks:
            logger.info(f"   失败列表: {', '.join(failed_stocks)}")

        # 5. 打印数据库统计
        stats = self.db.get_data_statistics()
        logger.info("\n=== 数据库统计 ===")
        logger.info(f"股票数量: {stats.get('stock_count', 0)}")
        logger.info(f"日线数据: {stats.get('ohlcv_records', 0)} 条")
        logger.info(f"技术指标: {stats.get('indicator_records', 0)} 条")
        logger.info(f"数据库大小: {stats.get('db_size_mb', 0)} MB")
        logger.info("="*60)

    def update_database(self, stock_codes: List[str] = None, incremental: bool = True):
        """
        更新数据库（增量更新）

        Args:
            stock_codes: 要更新的股票代码列表，None表示更新所有股票
            incremental: 是否增量更新（只更新缺失日期）
        """
        # 如果未指定股票列表，从数据库获取
        if stock_codes is None:
            stock_df = self.db.get_stock_list()
            if stock_df.empty:
                logger.error("数据库中无股票信息，请先执行初始化")
                return
            stock_codes = stock_df['ts_code'].tolist()

        logger.info(f"开始更新数据库，共 {len(stock_codes)} 只股票")

        # 确定结束日期：如果今天不是交易日，找到最近的交易日
        today = datetime.now()
        end_date = today.strftime('%Y%m%d')

        # 向前查找最近的交易日（最多查找10天）
        for i in range(10):
            check_date = (today - timedelta(days=i)).strftime('%Y%m%d')
            if self.is_trade_date(check_date):
                end_date = check_date
                if i > 0:
                    logger.info(f"今天({today.strftime('%Y%m%d')})不是交易日，使用最近交易日: {end_date}")
                break
        else:
            logger.warning("未找到最近的交易日，使用今天日期")
            end_date = today.strftime('%Y%m%d')

        success_count = 0
        failed_stocks = []

        for i, code in enumerate(stock_codes, 1):
            try:
                replace_existing = False

                # 增量更新：获取数据库中最新日期
                if incremental:
                    latest_date = self.db.get_latest_date(code)
                    if latest_date:
                        # 从最新日期的下一天开始更新
                        # 处理不同的日期格式（字符串或datetime对象）
                        if isinstance(latest_date, str):
                            # 如果是字符串，尝试解析（可能是YYYYMMDD或YYYY-MM-DD格式）
                            if '-' in latest_date or ' ' in latest_date:
                                start_date_dt = pd.to_datetime(latest_date) + timedelta(days=1)
                            else:
                                start_date_dt = datetime.strptime(latest_date, '%Y%m%d') + timedelta(days=1)
                        else:
                            # 如果已是datetime对象
                            start_date_dt = latest_date + timedelta(days=1)
                        start_date = start_date_dt.strftime('%Y%m%d')

                        # 如果数据库日期已追平，再检查历史记录中是否仍有缺失的
                        # daily_basic 必填字段。存在缺失值时，从最早缺失日期开始
                        # 重抓并覆盖该区间。
                        if start_date > end_date:
                            missing_daily_basic_range = self.db.get_missing_daily_basic_range(code)
                            missing_daily_basic_start = (
                                missing_daily_basic_range[0] if missing_daily_basic_range else None
                            )
                            if missing_daily_basic_start:
                                start_date = missing_daily_basic_start
                                replace_existing = True
                                logger.info(
                                    f"[{i}/{len(stock_codes)}] {code} 最新日期已齐，但存在缺失daily_basic必填字段，"
                                    f"从 {start_date} 开始重抓"
                                )
                            else:
                                logger.info(
                                    f"[{i}/{len(stock_codes)}] {code} 数据已是最新且daily_basic必填字段完整，跳过"
                                )
                                success_count += 1
                                continue
                    else:
                        # 数据库中无此股票，获取最近365天数据
                        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
                else:
                    # 全量更新最近365天
                    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')

                logger.info(f"[{i}/{len(stock_codes)}] 更新 {code} ({start_date} 至 {end_date})")

                if self.process_stock(code, start_date, end_date, replace=replace_existing):
                    success_count += 1
                else:
                    failed_stocks.append(code)

                # API限流
                time.sleep(0.15)

            except Exception as e:
                logger.error(f"❌ 更新 {code} 时发生错误: {e}")
                failed_stocks.append(code)
                continue

        # 输出统计
        logger.info("\n" + "="*60)
        logger.info("更新完成！")
        logger.info(f"✅ 成功: {success_count} 只")
        logger.info(f"❌ 失败: {len(failed_stocks)} 只")
        if failed_stocks:
            logger.info(f"   失败列表: {', '.join(failed_stocks)}")

        stats = self.db.get_data_statistics()
        logger.info(f"\n数据库总记录: {stats.get('ohlcv_records', 0)} 条")
        logger.info("="*60)

    def close(self):
        """关闭数据库连接"""
        self.db.close()


def read_stock_pool(pool_file: str) -> List[str]:
    """
    从股票池文件读取股票代码

    Args:
        pool_file: 股票池文件路径

    Returns:
        股票代码列表
    """
    if not os.path.exists(pool_file):
        logger.error(f"股票池文件不存在: {pool_file}")
        return []

    stock_codes = []
    with open(pool_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue
            # 提取股票代码（去掉注释部分）
            code = line.split('#')[0].strip()
            if code:
                stock_codes.append(code)

    logger.info(f"从 {pool_file} 读取到 {len(stock_codes)} 只股票")
    return stock_codes


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='从Tushare获取股票数据并存入本地数据库')

    parser.add_argument('--init', action='store_true',
                       help='初始化数据库（全量导入）')
    parser.add_argument('--update', action='store_true',
                       help='更新数据库（增量更新）')
    parser.add_argument('--pool', type=str,
                       help='股票池文件路径，默认使用stock_pool_example.txt')
    parser.add_argument('--codes', type=str,
                       help='指定股票代码，多个代码用逗号分隔，如: 688256.SH,603893.SH')
    parser.add_argument('--days', type=int, default=365,
                       help='初始化时获取最近N天的数据，默认365天')
    parser.add_argument('--db', type=str,
                       help='数据库文件路径，默认为项目根目录下的stock_data.db')

    args = parser.parse_args()

    # 至少指定一个操作
    if not args.init and not args.update:
        parser.print_help()
        print("\n错误: 请指定操作类型 --init 或 --update")
        return

    # 获取股票代码列表
    stock_codes = []
    if args.codes:
        # 从命令行参数获取
        stock_codes = [code.strip() for code in args.codes.split(',')]
    elif args.pool:
        # 从指定的股票池文件获取
        stock_codes = read_stock_pool(args.pool)
    else:
        # 使用默认股票池文件
        default_pool = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'stock_pool_example.txt'
        )
        if os.path.exists(default_pool):
            stock_codes = read_stock_pool(default_pool)
        else:
            logger.error("未找到股票池文件，请使用 --pool 或 --codes 参数指定股票")
            return

    if not stock_codes:
        logger.error("未获取到任何股票代码")
        return

    # 创建数据抓取器
    try:
        fetcher = DataFetcher(db_path=args.db)

        # 执行操作
        if args.init:
            fetcher.init_database(stock_codes, days=args.days)
        elif args.update:
            fetcher.update_database(stock_codes, incremental=True)

        fetcher.close()

    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
