"""
数据查询辅助类
提供与Tushare API兼容的查询接口，方便现有脚本无缝切换到本地数据库
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import logging
from database.db_manager import StockDatabase

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StockDataQuery:
    """股票数据查询类，提供与Tushare兼容的接口"""

    def __init__(self, db_path: str = None):
        """
        初始化查询类

        Args:
            db_path: 数据库文件路径
        """
        self.db = StockDatabase(db_path)
        logger.info("本地数据库查询已就绪")

    def daily(self, ts_code: str, start_date: str = None,
             end_date: str = None) -> Optional[pd.DataFrame]:
        """
        获取日线数据（兼容Tushare的pro.daily接口）

        Args:
            ts_code: 股票代码，如 '688256.SH'
            start_date: 开始日期，格式 YYYYMMDD 或 YYYY-MM-DD
            end_date: 结束日期，格式 YYYYMMDD 或 YYYY-MM-DD

        Returns:
            DataFrame，字段与Tushare保持一致
        """
        df = self.db.get_daily_ohlcv(ts_code, start_date, end_date)

        if df is None or df.empty:
            logger.warning(f"本地数据库中无 {ts_code} 的数据")
            return None

        # 移除数据库自增ID列
        if 'id' in df.columns:
            df = df.drop(columns=['id'])

        # 按日期升序排序（与Tushare习惯相反，但与现有脚本逻辑一致）
        df = df.sort_values('trade_date', ascending=True).reset_index(drop=True)

        return df

    def daily_with_indicators(self, ts_code: str, start_date: str = None,
                             end_date: str = None) -> Optional[pd.DataFrame]:
        """
        获取日线数据和技术指标（合并数据）

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            包含OHLCV和技术指标的完整DataFrame
        """
        df = self.db.get_combined_data(ts_code, start_date, end_date)

        if df is None or df.empty:
            logger.warning(f"本地数据库中无 {ts_code} 的数据")
            return None

        # 移除数据库自增ID列
        if 'id' in df.columns:
            df = df.drop(columns=['id'])

        return df

    def get_stock_data_for_analysis(self, ts_code: str, days: int = 60) -> Optional[pd.DataFrame]:
        """
        获取用于分析的股票数据（最近N天）
        这是一个便捷方法，专门为现有分析脚本设计

        Args:
            ts_code: 股票代码
            days: 获取最近N天的数据

        Returns:
            DataFrame，字段已重命名为pandas_ta所需格式（Open, High, Low, Close, Volume）
        """
        # 计算日期范围
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        # 获取数据
        df = self.daily(ts_code, start_date, end_date)

        if df is None or df.empty:
            return None

        # 字段重命名（适配pandas_ta）
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'vol': 'Volume'
        }, inplace=True)

        # 转换日期格式
        df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')

        return df

    def check_data_availability(self, ts_code: str) -> dict:
        """
        检查股票数据的可用性

        Args:
            ts_code: 股票代码

        Returns:
            包含数据统计信息的字典
        """
        min_date, max_date = self.db.get_date_range(ts_code)

        if min_date is None:
            return {
                'available': False,
                'message': f'本地数据库中无 {ts_code} 的数据'
            }

        # 计算数据天数
        ohlcv_df = self.db.get_daily_ohlcv(ts_code)
        record_count = len(ohlcv_df) if not ohlcv_df.empty else 0

        # 检查数据是否最新
        today = datetime.now().strftime('%Y%m%d')
        is_latest = (max_date >= today or
                    (datetime.now().weekday() >= 5) or  # 周末
                    max_date >= (datetime.now() - timedelta(days=3)).strftime('%Y%m%d'))  # 3天内

        return {
            'available': True,
            'ts_code': ts_code,
            'start_date': min_date,
            'end_date': max_date,
            'record_count': record_count,
            'is_latest': is_latest,
            'message': f'数据范围: {min_date} 至 {max_date}，共 {record_count} 条记录'
        }

    def close(self):
        """关闭数据库连接"""
        self.db.close()

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器时关闭连接"""
        self.close()


# 全局单例，方便导入使用
_global_query = None


def get_query(db_path: str = None) -> StockDataQuery:
    """
    获取全局查询实例（单例模式）

    Args:
        db_path: 数据库文件路径

    Returns:
        StockDataQuery实例
    """
    global _global_query
    if _global_query is None:
        _global_query = StockDataQuery(db_path)
    return _global_query


# 便捷函数，直接替代 pro.daily()
def daily(ts_code: str, start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
    """
    便捷函数：获取日线数据
    可以直接替代 pro.daily() 调用

    使用示例:
        from database.query_helper import daily
        df = daily('688256.SH', start_date='20230101', end_date='20231231')

    Args:
        ts_code: 股票代码
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        DataFrame
    """
    query = get_query()
    return query.daily(ts_code, start_date, end_date)


if __name__ == '__main__':
    # 测试代码
    print("=== 测试本地数据库查询 ===\n")

    query = StockDataQuery()

    # 测试股票代码
    test_code = '688256.SH'

    # 1. 检查数据可用性
    print(f"1. 检查 {test_code} 数据可用性:")
    availability = query.check_data_availability(test_code)
    print(f"   {availability.get('message', '无数据')}")
    print()

    if availability.get('available'):
        # 2. 获取最近30天数据
        print(f"2. 获取 {test_code} 最近30天数据:")
        df = query.get_stock_data_for_analysis(test_code, days=30)
        if df is not None and not df.empty:
            print(f"   数据行数: {len(df)}")
            print(f"   字段: {', '.join(df.columns.tolist())}")
            print(f"   最新日期: {df['trade_date'].max()}")
            print(f"   最新收盘价: {df['Close'].iloc[-1]:.2f}")
        else:
            print("   无数据")
        print()

        # 3. 测试原始daily接口
        print(f"3. 测试 daily() 接口:")
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
        df_daily = query.daily(test_code, start_date, end_date)
        if df_daily is not None and not df_daily.empty:
            print(f"   获取到 {len(df_daily)} 条数据")
            print(f"   字段: {', '.join(df_daily.columns.tolist())}")
        else:
            print("   无数据")

    query.close()
    print("\n测试完成")
