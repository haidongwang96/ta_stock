"""
股票数据库管理类
提供SQLite数据库的创建、数据插入、更新和查询功能
"""

import sqlite3
import pandas as pd
import os
import json
from datetime import datetime
from typing import Optional, List, Tuple
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DAILY_BASIC_FIELDS = [
    'turnover_rate',
    'turnover_rate_f',
    'volume_ratio',
    'pe',
    'pe_ttm',
    'pb',
    'ps',
    'ps_ttm',
    'dv_ratio',
    'dv_ttm',
    'total_share',
    'float_share',
    'free_share',
    'total_mv',
    'circ_mv',
]

DAILY_BASIC_REQUIRED_FIELDS = [
    'turnover_rate',
    'turnover_rate_f',
    'volume_ratio',
    'total_share',
    'float_share',
    'free_share',
    'total_mv',
    'circ_mv',
]


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
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA cache_size=-20000")
            self.conn.execute("PRAGMA temp_store=MEMORY")
            logger.info(f"数据库连接成功: {self.db_path}")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def _stock_basic_needs_migration(self) -> bool:
        """检查 stock_basic 是否缺少主键约束。"""
        cursor = self.conn.execute("PRAGMA table_info(stock_basic)")
        table_info = cursor.fetchall()
        if not table_info:
            return False

        ts_code_rows = [row for row in table_info if row[1] == 'ts_code']
        if not ts_code_rows:
            return True

        return ts_code_rows[0][5] != 1

    def _migrate_stock_basic_schema(self):
        """将旧的 stock_basic 表迁移为带主键约束的结构。"""
        if not self._stock_basic_needs_migration():
            return

        cursor = self.conn.cursor()
        logger.info("检测到 stock_basic 缺少主键约束，开始迁移表结构")

        cursor.execute("ALTER TABLE stock_basic RENAME TO stock_basic_old")
        cursor.execute('''
            CREATE TABLE stock_basic (
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
        cursor.execute('''
            INSERT OR REPLACE INTO stock_basic (
                ts_code, symbol, name, area, industry, market, list_date, update_time
            )
            SELECT
                ts_code, symbol, name, area, industry, market, list_date, update_time
            FROM stock_basic_old
            WHERE ts_code IS NOT NULL
            ORDER BY rowid
        ''')
        cursor.execute("DROP TABLE stock_basic_old")
        self.conn.commit()
        logger.info("stock_basic 表结构迁移完成")

    def _drop_redundant_indexes(self):
        """删除与 UNIQUE 约束重复的复合索引，降低写入开销。"""
        redundant_indexes = [
            "idx_daily_ohlcv_code_date",
            "idx_daily_indicators_code_date",
        ]
        for index_name in redundant_indexes:
            self.conn.execute(f"DROP INDEX IF EXISTS {index_name}")

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
        self._migrate_stock_basic_schema()

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
                adj_factor REAL,
                turnover_rate REAL,
                turnover_rate_f REAL,
                volume_ratio REAL,
                pe REAL,
                pe_ttm REAL,
                pb REAL,
                ps REAL,
                ps_ttm REAL,
                dv_ratio REAL,
                dv_ttm REAL,
                total_share REAL,
                float_share REAL,
                free_share REAL,
                total_mv REAL,
                circ_mv REAL,
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
                -- VSA量价分析指标
                vma20 REAL,
                volume_multiple REAL,
                -- 波动率
                atr REAL,
                -- 趋势指标
                sar REAL,
                UNIQUE(ts_code, trade_date)
            )
        ''')

        # 为已存在的表添加新字段（如果字段不存在）
        try:
            cursor.execute("ALTER TABLE daily_indicators ADD COLUMN vma20 REAL")
            logger.info("成功添加vma20字段")
        except sqlite3.OperationalError:
            # 字段已存在，忽略
            pass

        try:
            cursor.execute("ALTER TABLE daily_indicators ADD COLUMN volume_multiple REAL")
            logger.info("成功添加volume_multiple字段")
        except sqlite3.OperationalError:
            # 字段已存在，忽略
            pass

        # 为 daily_ohlcv 添加 daily_basic 扩展字段（兼容旧数据库）
        try:
            cursor.execute("ALTER TABLE daily_ohlcv ADD COLUMN adj_factor REAL")
            logger.info("成功添加adj_factor字段")
        except sqlite3.OperationalError:
            pass

        for field in DAILY_BASIC_FIELDS:
            try:
                cursor.execute(f"ALTER TABLE daily_ohlcv ADD COLUMN {field} REAL")
                logger.info(f"成功添加{field}字段")
            except sqlite3.OperationalError:
                pass

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

        # 5. 技术形态分析结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_pattern_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                stock_name TEXT,
                close REAL,
                change_pct REAL,
                pct_5d REAL,
                pct_10d REAL,
                pct_20d REAL,
                source TEXT,
                indicators_json TEXT,
                patterns_json TEXT,
                year_stats_json TEXT,
                analysis_payload TEXT NOT NULL,
                analysis_version TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(ts_code, trade_date)
            )
        ''')

        for field in ['pct_5d', 'pct_10d', 'pct_20d']:
            try:
                cursor.execute(f"ALTER TABLE daily_pattern_analysis ADD COLUMN {field} REAL")
                logger.info(f"成功添加{field}字段")
            except sqlite3.OperationalError:
                pass

        # 创建索引以提高查询性能
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_date
            ON daily_ohlcv(trade_date)
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

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_daily_pattern_analysis_code
            ON daily_pattern_analysis(ts_code)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_daily_pattern_analysis_date
            ON daily_pattern_analysis(trade_date)
        ''')

        self._drop_redundant_indexes()
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
            self.conn.execute("DELETE FROM stock_basic")
            stock_info.to_sql(
                'stock_basic',
                self.conn,
                if_exists='append',
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

    def save_pattern_analysis_results(
        self,
        results: List[dict],
        source: str = 'local_db',
        analysis_version: str = 'stock_analysis_v1',
        replace: bool = True,
    ):
        """
        保存技术形态分析结果。

        Args:
            results: stock_analysis.py 产生的结果列表
            source: 数据来源标记
            analysis_version: 分析结果版本号
            replace: 是否覆盖同股票同交易日旧记录
        """
        if not results:
            logger.warning("分析结果为空，跳过保存")
            return

        rows = []
        updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for result in results:
            ts_code = result.get('code')
            trade_date = result.get('date')
            if not ts_code or not trade_date:
                logger.warning("分析结果缺少 code/date，已跳过一条记录")
                continue

            rows.append({
                'ts_code': ts_code,
                'trade_date': str(trade_date),
                'stock_name': result.get('name'),
                'close': result.get('close'),
                'change_pct': result.get('change_pct'),
                'pct_5d': result.get('pct_5d'),
                'pct_10d': result.get('pct_10d'),
                'pct_20d': result.get('pct_20d'),
                'source': source,
                'indicators_json': json.dumps(result.get('indicators', {}), ensure_ascii=False),
                'patterns_json': json.dumps(result.get('patterns', {}), ensure_ascii=False),
                'year_stats_json': json.dumps(result.get('year_stats', {}), ensure_ascii=False),
                'analysis_payload': json.dumps(result, ensure_ascii=False),
                'analysis_version': analysis_version,
                'updated_at': updated_at,
            })

        if not rows:
            logger.warning("没有可保存的分析结果")
            return

        df = pd.DataFrame(rows)

        try:
            if replace:
                for _, row in df.iterrows():
                    self.conn.execute(
                        "DELETE FROM daily_pattern_analysis WHERE ts_code = ? AND trade_date = ?",
                        (row['ts_code'], row['trade_date']),
                    )

            df.to_sql(
                'daily_pattern_analysis',
                self.conn,
                if_exists='append',
                index=False,
                method='multi'
            )
            self.conn.commit()
            logger.info(f"成功保存 {len(df)} 条技术形态分析结果")
        except sqlite3.IntegrityError:
            logger.warning("部分技术形态分析结果已存在，跳过重复数据")
            self.conn.rollback()
        except Exception as e:
            logger.error(f"保存技术形态分析结果失败: {e}")
            self.conn.rollback()
            raise

    def get_pattern_analysis(
        self,
        ts_code: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> pd.DataFrame:
        """
        查询技术形态分析结果。
        """
        if start_date and '-' in start_date:
            start_date = start_date.replace('-', '')
        if end_date and '-' in end_date:
            end_date = end_date.replace('-', '')

        query = "SELECT * FROM daily_pattern_analysis WHERE 1=1"
        params = []

        if ts_code:
            query += " AND ts_code = ?"
            params.append(ts_code)
        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date DESC, ts_code ASC"

        try:
            return pd.read_sql_query(query, self.conn, params=params)
        except Exception as e:
            logger.error(f"查询技术形态分析结果失败: {e}")
            return pd.DataFrame()

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

    def get_missing_daily_basic_range(self, ts_code: str) -> Tuple[Optional[str], Optional[str]]:
        """
        获取指定股票中缺失 daily_basic 必填扩展字段的数据范围。

        Args:
            ts_code: 股票代码

        Returns:
            (最早缺失日期, 最晚缺失日期) 元组；如果不存在缺失值则返回 (None, None)
        """
        try:
            missing_conditions = " OR ".join(
                f"{field} IS NULL" for field in DAILY_BASIC_REQUIRED_FIELDS
            )
            query = """
                SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date
                FROM daily_ohlcv
                WHERE ts_code = ?
                  AND ({missing_conditions})
            """.format(missing_conditions=missing_conditions)
            cursor = self.conn.execute(query, (ts_code,))
            result = cursor.fetchone()
            return (result[0], result[1]) if result and result[0] else (None, None)
        except Exception as e:
            logger.error(f"查询缺失daily_basic必填字段区间失败 ({ts_code}): {e}")
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
            cursor.execute("DELETE FROM daily_pattern_analysis WHERE ts_code = ?", (ts_code,))
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

            # 技术形态分析记录数
            cursor = self.conn.execute("SELECT COUNT(*) FROM daily_pattern_analysis")
            stats['pattern_analysis_records'] = cursor.fetchone()[0]

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
