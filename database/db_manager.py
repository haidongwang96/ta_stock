"""
股票数据库管理类
提供SQLite数据库的创建、数据插入、更新和查询功能
"""

import sqlite3
import pandas as pd
import os
from datetime import datetime
from typing import Optional, List, Tuple
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StockDatabase:
    """股票数据库管理类"""

    def __init__(self, db_path: str = None):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径，默认为项目根目录下的stock_data.db
        """
        if db_path is None:
            # 默认数据库路径为项目根目录
            project_root = os.path.dirname(os.path.dirname(__file__))
            db_path = os.path.join(project_root, 'stock_data.db')

        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """建立数据库连接"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            logger.info(f"数据库连接成功: {self.db_path}")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def _create_tables(self):
        """创建所有必需的表"""
        cursor = self.conn.cursor()

        # 1. 股票基本信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_basic (
                ts_code TEXT PRIMARY KEY,
                symbol TEXT,
                name TEXT,
                area TEXT,
                industry TEXT,
                market TEXT,
                list_date TEXT,
                update_time TEXT
            )
        ''')

        # 2. 日线OHLCV原始数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_ohlcv (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                pre_close REAL,
                change REAL,
                pct_chg REAL,
                vol REAL,
                amount REAL,
                UNIQUE(ts_code, trade_date)
            )
        ''')

        # 3. 技术指标数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_indicators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                -- 均线指标
                ma5 REAL,
                ma10 REAL,
                ma20 REAL,
                ma60 REAL,
                -- MACD指标
                macd_dif REAL,
                macd_dea REAL,
                macd_hist REAL,
                -- 动量指标
                rsi REAL,
                kdj_k REAL,
                kdj_d REAL,
                kdj_j REAL,
                cci REAL,
                -- 布林带
                boll_upper REAL,
                boll_mid REAL,
                boll_lower REAL,
                boll_width REAL,
                -- 成交量指标
                obv REAL,
                mfi REAL,
                vwap REAL,
                vol_ratio REAL,
                -- 波动率
                atr REAL,
                -- 趋势指标
                sar REAL,
                UNIQUE(ts_code, trade_date)
            )
        ''')

        # 4. 滚动窗口打分数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rolling_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL,
                next_date TEXT,
                change_pct REAL,
                -- 得分数据
                total_score REAL,
                trend_score REAL,
                momentum_score REAL,
                volatility_score REAL,
                volume_score REAL,
                pattern_score REAL,
                score_level TEXT,
                -- 关键指标
                rsi REAL,
                mfi REAL,
                k REAL,
                d REAL,
                j REAL,
                cci REAL,
                atr REAL,
                volume_ratio REAL,
                -- 详细信息
                score_details TEXT,
                signals TEXT,
                -- 元数据
                updated_at TEXT,
                UNIQUE(ts_code, trade_date)
            )
        ''')

        # 创建索引以提高查询性能
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_code_date
            ON daily_ohlcv(ts_code, trade_date)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_date
            ON daily_ohlcv(trade_date)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_daily_indicators_code_date
            ON daily_indicators(ts_code, trade_date)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_daily_indicators_date
            ON daily_indicators(trade_date)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_rolling_scores_code
            ON rolling_scores(ts_code)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_rolling_scores_date
            ON rolling_scores(trade_date)
        ''')

        self.conn.commit()
        logger.info("数据表创建/检查完成")

    def insert_stock_basic(self, stock_info: pd.DataFrame):
        """
        插入或更新股票基本信息

        Args:
            stock_info: 包含股票基本信息的DataFrame
        """
        stock_info['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            stock_info.to_sql(
                'stock_basic',
                self.conn,
                if_exists='replace',
                index=False,
                method='multi'
            )
            logger.info(f"成功插入/更新 {len(stock_info)} 条股票基本信息")
        except Exception as e:
            logger.error(f"插入股票基本信息失败: {e}")
            raise

    def insert_daily_ohlcv(self, data: pd.DataFrame, replace: bool = False):
        """
        插入日线OHLCV数据

        Args:
            data: 包含OHLCV数据的DataFrame
            replace: 如果为True，则替换已存在的数据；否则忽略重复数据
        """
        if data is None or data.empty:
            logger.warning("数据为空，跳过插入")
            return

        # 确保必需字段存在
        required_columns = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            logger.error(f"缺少必需字段: {missing_columns}")
            return

        try:
            if replace:
                # 删除已存在的数据
                for _, row in data.iterrows():
                    self.conn.execute(
                        "DELETE FROM daily_ohlcv WHERE ts_code=? AND trade_date=?",
                        (row['ts_code'], row['trade_date'])
                    )

            # 插入数据
            data.to_sql(
                'daily_ohlcv',
                self.conn,
                if_exists='append',
                index=False,
                method='multi'
            )
            self.conn.commit()
            logger.info(f"成功插入 {len(data)} 条日线数据")
        except sqlite3.IntegrityError:
            logger.warning("部分数据已存在，跳过重复数据")
            self.conn.rollback()
        except Exception as e:
            logger.error(f"插入日线数据失败: {e}")
            self.conn.rollback()
            raise

    def insert_daily_indicators(self, data: pd.DataFrame, replace: bool = False):
        """
        插入技术指标数据

        Args:
            data: 包含技术指标的DataFrame
            replace: 如果为True，则替换已存在的数据；否则忽略重复数据
        """
        if data is None or data.empty:
            logger.warning("数据为空，跳过插入")
            return

        try:
            if replace:
                # 删除已存在的数据
                for _, row in data.iterrows():
                    self.conn.execute(
                        "DELETE FROM daily_indicators WHERE ts_code=? AND trade_date=?",
                        (row['ts_code'], row['trade_date'])
                    )

            # 插入数据
            data.to_sql(
                'daily_indicators',
                self.conn,
                if_exists='append',
                index=False,
                method='multi'
            )
            self.conn.commit()
            logger.info(f"成功插入 {len(data)} 条技术指标数据")
        except sqlite3.IntegrityError:
            logger.warning("部分数据已存在，跳过重复数据")
            self.conn.rollback()
        except Exception as e:
            logger.error(f"插入技术指标数据失败: {e}")
            self.conn.rollback()
            raise

    def get_stock_list(self) -> pd.DataFrame:
        """
        获取所有股票列表

        Returns:
            包含股票基本信息的DataFrame
        """
        try:
            query = "SELECT * FROM stock_basic"
            df = pd.read_sql_query(query, self.conn)
            return df
        except Exception as e:
            logger.error(f"查询股票列表失败: {e}")
            return pd.DataFrame()

    def get_daily_ohlcv(self, ts_code: str, start_date: str = None,
                        end_date: str = None) -> pd.DataFrame:
        """
        获取指定股票的日线数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期 YYYYMMDD 或 YYYY-MM-DD
            end_date: 结束日期 YYYYMMDD 或 YYYY-MM-DD

        Returns:
            包含OHLCV数据的DataFrame
        """
        # 统一日期格式为YYYYMMDD
        if start_date and '-' in start_date:
            start_date = start_date.replace('-', '')
        if end_date and '-' in end_date:
            end_date = end_date.replace('-', '')

        query = "SELECT * FROM daily_ohlcv WHERE ts_code = ?"
        params = [ts_code]

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date ASC"

        try:
            df = pd.read_sql_query(query, self.conn, params=params)
            return df
        except Exception as e:
            logger.error(f"查询日线数据失败 ({ts_code}): {e}")
            return pd.DataFrame()

    def get_daily_indicators(self, ts_code: str, start_date: str = None,
                            end_date: str = None) -> pd.DataFrame:
        """
        获取指定股票的技术指标数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期 YYYYMMDD 或 YYYY-MM-DD
            end_date: 结束日期 YYYYMMDD 或 YYYY-MM-DD

        Returns:
            包含技术指标的DataFrame
        """
        # 统一日期格式
        if start_date and '-' in start_date:
            start_date = start_date.replace('-', '')
        if end_date and '-' in end_date:
            end_date = end_date.replace('-', '')

        query = "SELECT * FROM daily_indicators WHERE ts_code = ?"
        params = [ts_code]

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date ASC"

        try:
            df = pd.read_sql_query(query, self.conn, params=params)
            return df
        except Exception as e:
            logger.error(f"查询技术指标数据失败 ({ts_code}): {e}")
            return pd.DataFrame()

    def get_combined_data(self, ts_code: str, start_date: str = None,
                         end_date: str = None) -> pd.DataFrame:
        """
        获取OHLCV和技术指标的合并数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            包含OHLCV和技术指标的完整DataFrame
        """
        ohlcv_df = self.get_daily_ohlcv(ts_code, start_date, end_date)
        indicators_df = self.get_daily_indicators(ts_code, start_date, end_date)

        if ohlcv_df.empty:
            logger.warning(f"{ts_code} 无日线数据")
            return pd.DataFrame()

        if not indicators_df.empty:
            # 合并数据，以trade_date为键
            merged_df = pd.merge(
                ohlcv_df,
                indicators_df.drop(columns=['id', 'ts_code'], errors='ignore'),
                on='trade_date',
                how='left'
            )
            return merged_df
        else:
            logger.warning(f"{ts_code} 无技术指标数据")
            return ohlcv_df

    def get_latest_date(self, ts_code: str = None) -> Optional[str]:
        """
        获取数据库中最新的交易日期

        Args:
            ts_code: 股票代码，如果为None则查询所有股票的最新日期

        Returns:
            最新交易日期 YYYYMMDD格式，如果无数据则返回None
        """
        try:
            if ts_code:
                query = "SELECT MAX(trade_date) as max_date FROM daily_ohlcv WHERE ts_code = ?"
                cursor = self.conn.execute(query, (ts_code,))
            else:
                query = "SELECT MAX(trade_date) as max_date FROM daily_ohlcv"
                cursor = self.conn.execute(query)

            result = cursor.fetchone()
            return result[0] if result[0] else None
        except Exception as e:
            logger.error(f"查询最新日期失败: {e}")
            return None

    def get_date_range(self, ts_code: str) -> Tuple[Optional[str], Optional[str]]:
        """
        获取指定股票的数据日期范围

        Args:
            ts_code: 股票代码

        Returns:
            (最早日期, 最新日期) 元组，YYYYMMDD格式
        """
        try:
            query = """
                SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date
                FROM daily_ohlcv
                WHERE ts_code = ?
            """
            cursor = self.conn.execute(query, (ts_code,))
            result = cursor.fetchone()
            return (result[0], result[1]) if result else (None, None)
        except Exception as e:
            logger.error(f"查询日期范围失败: {e}")
            return (None, None)

    def delete_stock_data(self, ts_code: str):
        """
        删除指定股票的所有数据

        Args:
            ts_code: 股票代码
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM daily_ohlcv WHERE ts_code = ?", (ts_code,))
            cursor.execute("DELETE FROM daily_indicators WHERE ts_code = ?", (ts_code,))
            cursor.execute("DELETE FROM stock_basic WHERE ts_code = ?", (ts_code,))
            self.conn.commit()
            logger.info(f"成功删除 {ts_code} 的所有数据")
        except Exception as e:
            logger.error(f"删除数据失败: {e}")
            self.conn.rollback()
            raise

    def get_data_statistics(self) -> dict:
        """
        获取数据库统计信息

        Returns:
            包含统计信息的字典
        """
        stats = {}

        try:
            # 股票数量
            cursor = self.conn.execute("SELECT COUNT(*) FROM stock_basic")
            stats['stock_count'] = cursor.fetchone()[0]

            # 日线数据记录数
            cursor = self.conn.execute("SELECT COUNT(*) FROM daily_ohlcv")
            stats['ohlcv_records'] = cursor.fetchone()[0]

            # 技术指标记录数
            cursor = self.conn.execute("SELECT COUNT(*) FROM daily_indicators")
            stats['indicator_records'] = cursor.fetchone()[0]

            # 日期范围
            cursor = self.conn.execute(
                "SELECT MIN(trade_date), MAX(trade_date) FROM daily_ohlcv"
            )
            result = cursor.fetchone()
            stats['date_range'] = (result[0], result[1]) if result else (None, None)

            # 数据库文件大小
            if os.path.exists(self.db_path):
                size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
                stats['db_size_mb'] = round(size_mb, 2)

            return stats
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return stats

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器时关闭连接"""
        self.close()


if __name__ == '__main__':
    # 测试代码
    db = StockDatabase()

    # 打印统计信息
    stats = db.get_data_statistics()
    print("\n=== 数据库统计信息 ===")
    print(f"股票数量: {stats.get('stock_count', 0)}")
    print(f"日线数据记录数: {stats.get('ohlcv_records', 0)}")
    print(f"技术指标记录数: {stats.get('indicator_records', 0)}")
    print(f"日期范围: {stats.get('date_range', (None, None))}")
    print(f"数据库大小: {stats.get('db_size_mb', 0)} MB")

    db.close()
