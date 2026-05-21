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

FINANCIAL_DERIVED_FIELDS = [
    'deducted_profit',
    'operating_cash_flow',
    'ocf_to_profit',
    'roe',
    'roic',
    'debt_to_assets',
    'sales_expense',
    'admin_expense',
    'rd_expense',
    'sales_expense_rate',
    'admin_expense_rate',
    'rd_expense_rate',
    'quarter_profit',
    'quarter_revenue',
    'quarter_deducted_profit',
    'quarter_operating_cash_flow',
    'quarter_gross_margin',
    'quarter_net_margin',
    'quarter_ocf_to_profit',
    'quarter_sales_expense_rate',
    'quarter_admin_expense_rate',
    'quarter_rd_expense_rate',
    'profit_yoy',
    'profit_qoq',
    'revenue_yoy',
    'revenue_qoq',
    'deducted_profit_yoy',
    'deducted_profit_qoq',
    'operating_cash_flow_yoy',
    'operating_cash_flow_qoq',
    'gross_margin_yoy',
    'gross_margin_qoq',
    'net_margin_yoy',
    'net_margin_qoq',
    'ocf_to_profit_yoy',
    'ocf_to_profit_qoq',
    'roe_yoy',
    'roe_qoq',
    'roic_yoy',
    'roic_qoq',
    'debt_to_assets_yoy',
    'debt_to_assets_qoq',
    'sales_expense_rate_yoy',
    'sales_expense_rate_qoq',
    'admin_expense_rate_yoy',
    'admin_expense_rate_qoq',
    'rd_expense_rate_yoy',
    'rd_expense_rate_qoq',
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

        # 6. 财务指标表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT NOT NULL,
                report_date TEXT NOT NULL,
                end_date TEXT,
                period_type TEXT,
                profit REAL,
                revenue REAL,
                gross_margin REAL,
                net_margin REAL,
                deducted_profit REAL,
                operating_cash_flow REAL,
                ocf_to_profit REAL,
                roe REAL,
                roic REAL,
                debt_to_assets REAL,
                sales_expense REAL,
                admin_expense REAL,
                rd_expense REAL,
                sales_expense_rate REAL,
                admin_expense_rate REAL,
                rd_expense_rate REAL,
                quarter_profit REAL,
                quarter_revenue REAL,
                quarter_deducted_profit REAL,
                quarter_operating_cash_flow REAL,
                quarter_gross_margin REAL,
                quarter_net_margin REAL,
                quarter_ocf_to_profit REAL,
                quarter_sales_expense_rate REAL,
                quarter_admin_expense_rate REAL,
                quarter_rd_expense_rate REAL,
                profit_yoy REAL,
                profit_qoq REAL,
                revenue_yoy REAL,
                revenue_qoq REAL,
                deducted_profit_yoy REAL,
                deducted_profit_qoq REAL,
                operating_cash_flow_yoy REAL,
                operating_cash_flow_qoq REAL,
                gross_margin_yoy REAL,
                gross_margin_qoq REAL,
                net_margin_yoy REAL,
                net_margin_qoq REAL,
                ocf_to_profit_yoy REAL,
                ocf_to_profit_qoq REAL,
                roe_yoy REAL,
                roe_qoq REAL,
                roic_yoy REAL,
                roic_qoq REAL,
                debt_to_assets_yoy REAL,
                debt_to_assets_qoq REAL,
                sales_expense_rate_yoy REAL,
                sales_expense_rate_qoq REAL,
                admin_expense_rate_yoy REAL,
                admin_expense_rate_qoq REAL,
                rd_expense_rate_yoy REAL,
                rd_expense_rate_qoq REAL,
                updated_at TEXT,
                UNIQUE(ts_code, report_date, end_date, period_type)
            )
        ''')

        for field in FINANCIAL_DERIVED_FIELDS:
            try:
                cursor.execute(f"ALTER TABLE financial_metrics ADD COLUMN {field} REAL")
                logger.info(f"成功添加{field}字段")
            except sqlite3.OperationalError:
                pass

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

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_financial_metrics_code_report
            ON financial_metrics(ts_code, report_date DESC)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_financial_metrics_end_date
            ON financial_metrics(end_date)
        ''')

        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_financial_metrics_unique_report
            ON financial_metrics(
                ts_code,
                report_date,
                COALESCE(end_date, ''),
                COALESCE(period_type, '')
            )
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

    def insert_financial_metrics(self, data: pd.DataFrame, replace: bool = False):
        """
        插入财务指标数据。

        Args:
            data: 包含财务指标的DataFrame
            replace: 如果为True，则替换同股票同报告记录；否则忽略重复数据
        """
        if data is None or data.empty:
            logger.warning("财务指标数据为空，跳过插入")
            return

        required_columns = ['ts_code', 'report_date']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            logger.error(f"财务指标缺少必需字段: {missing_columns}")
            return

        df = data.copy()
        if 'updated_at' not in df.columns:
            df['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            if replace:
                for _, row in df.iterrows():
                    self.conn.execute(
                        """
                        DELETE FROM financial_metrics
                        WHERE ts_code = ?
                          AND report_date = ?
                          AND COALESCE(end_date, '') = COALESCE(?, '')
                          AND COALESCE(period_type, '') = COALESCE(?, '')
                        """,
                        (
                            row['ts_code'],
                            row['report_date'],
                            row.get('end_date'),
                            row.get('period_type'),
                        ),
                    )

            df.to_sql(
                'financial_metrics',
                self.conn,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=500,
            )
            self.conn.commit()
            logger.info(f"成功插入 {len(df)} 条财务指标数据")
        except sqlite3.IntegrityError:
            logger.warning("部分财务指标已存在，跳过重复数据")
            self.conn.rollback()
        except Exception as e:
            logger.error(f"插入财务指标失败: {e}")
            self.conn.rollback()
            raise

    def get_financial_metrics(
        self,
        ts_code: str,
        start_report_date: str = None,
        end_report_date: str = None,
        latest_only: bool = False,
    ) -> pd.DataFrame:
        """
        获取指定股票的财务指标数据。

        Args:
            ts_code: 股票代码
            start_report_date: 最早公告/报告日期 YYYYMMDD 或 YYYY-MM-DD
            end_report_date: 最晚公告/报告日期 YYYYMMDD 或 YYYY-MM-DD
            latest_only: 是否只返回最新一条
        """
        if start_report_date and '-' in start_report_date:
            start_report_date = start_report_date.replace('-', '')
        if end_report_date and '-' in end_report_date:
            end_report_date = end_report_date.replace('-', '')

        query = "SELECT * FROM financial_metrics WHERE ts_code = ?"
        params = [ts_code]

        if start_report_date:
            query += " AND report_date >= ?"
            params.append(start_report_date)
        if end_report_date:
            query += " AND report_date <= ?"
            params.append(end_report_date)

        query += " ORDER BY report_date DESC, end_date DESC"
        if latest_only:
            query += " LIMIT 1"

        try:
            return pd.read_sql_query(query, self.conn, params=params)
        except Exception as e:
            logger.error(f"查询财务指标失败 ({ts_code}): {e}")
            return pd.DataFrame()

    def get_latest_financial_metrics(self, ts_code: str) -> pd.DataFrame:
        """
        获取指定股票最新一条财务指标。
        """
        return self.get_financial_metrics(ts_code, latest_only=True)

    def update_financial_growth_metrics(self, ts_codes: List[str] = None) -> int:
        """
        基于累计财报数据计算单季值、同比和环比。

        利润/营收先拆成单季值：
        Q1 = Q1；Q2 = H1 - Q1；Q3 = Q3 - H1；Q4 = FY - Q3。
        毛利率先用 revenue * gross_margin 还原累计毛利额，再拆单季毛利率。
        净利率用单季利润 / 单季营收计算。
        利润/营收同比环比为百分比，毛利率/净利率同比环比为百分点变化。
        """
        query = "SELECT * FROM financial_metrics"
        params = []
        if ts_codes:
            placeholders = ",".join(["?"] * len(ts_codes))
            query += f" WHERE ts_code IN ({placeholders})"
            params.extend(ts_codes)

        try:
            df = pd.read_sql_query(query, self.conn, params=params)
        except Exception as e:
            logger.error(f"读取财务指标用于增长率计算失败: {e}")
            return 0

        if df.empty:
            logger.info("没有财务指标数据可计算同比环比")
            return 0

        updates = []
        for _, group in df.groupby('ts_code'):
            updates.extend(self._calculate_financial_growth_for_stock(group))

        if not updates:
            logger.info("没有可更新的财务同比环比数据")
            return 0

        update_sql = """
            UPDATE financial_metrics
            SET quarter_profit = ?,
                quarter_revenue = ?,
                quarter_deducted_profit = ?,
                quarter_operating_cash_flow = ?,
                quarter_gross_margin = ?,
                quarter_net_margin = ?,
                quarter_ocf_to_profit = ?,
                quarter_sales_expense_rate = ?,
                quarter_admin_expense_rate = ?,
                quarter_rd_expense_rate = ?,
                profit_yoy = ?,
                profit_qoq = ?,
                revenue_yoy = ?,
                revenue_qoq = ?,
                deducted_profit_yoy = ?,
                deducted_profit_qoq = ?,
                operating_cash_flow_yoy = ?,
                operating_cash_flow_qoq = ?,
                gross_margin_yoy = ?,
                gross_margin_qoq = ?,
                net_margin_yoy = ?,
                net_margin_qoq = ?,
                ocf_to_profit_yoy = ?,
                ocf_to_profit_qoq = ?,
                roe_yoy = ?,
                roe_qoq = ?,
                roic_yoy = ?,
                roic_qoq = ?,
                debt_to_assets_yoy = ?,
                debt_to_assets_qoq = ?,
                sales_expense_rate_yoy = ?,
                sales_expense_rate_qoq = ?,
                admin_expense_rate_yoy = ?,
                admin_expense_rate_qoq = ?,
                rd_expense_rate_yoy = ?,
                rd_expense_rate_qoq = ?,
                updated_at = ?
            WHERE id = ?
        """
        updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        payload = [
            (
                row['quarter_profit'],
                row['quarter_revenue'],
                row['quarter_deducted_profit'],
                row['quarter_operating_cash_flow'],
                row['quarter_gross_margin'],
                row['quarter_net_margin'],
                row['quarter_ocf_to_profit'],
                row['quarter_sales_expense_rate'],
                row['quarter_admin_expense_rate'],
                row['quarter_rd_expense_rate'],
                row['profit_yoy'],
                row['profit_qoq'],
                row['revenue_yoy'],
                row['revenue_qoq'],
                row['deducted_profit_yoy'],
                row['deducted_profit_qoq'],
                row['operating_cash_flow_yoy'],
                row['operating_cash_flow_qoq'],
                row['gross_margin_yoy'],
                row['gross_margin_qoq'],
                row['net_margin_yoy'],
                row['net_margin_qoq'],
                row['ocf_to_profit_yoy'],
                row['ocf_to_profit_qoq'],
                row['roe_yoy'],
                row['roe_qoq'],
                row['roic_yoy'],
                row['roic_qoq'],
                row['debt_to_assets_yoy'],
                row['debt_to_assets_qoq'],
                row['sales_expense_rate_yoy'],
                row['sales_expense_rate_qoq'],
                row['admin_expense_rate_yoy'],
                row['admin_expense_rate_qoq'],
                row['rd_expense_rate_yoy'],
                row['rd_expense_rate_qoq'],
                updated_at,
                row['id'],
            )
            for row in updates
        ]

        try:
            self.conn.executemany(update_sql, payload)
            self.conn.commit()
            logger.info(f"成功更新 {len(payload)} 条财务同比环比指标")
            return len(payload)
        except Exception as e:
            logger.error(f"更新财务同比环比指标失败: {e}")
            self.conn.rollback()
            raise

    def _calculate_financial_growth_for_stock(self, group: pd.DataFrame) -> List[dict]:
        group = group.copy()
        group['period_year'] = group['end_date'].astype(str).str[:4].astype(int)
        group['period_suffix'] = group['end_date'].astype(str).str[4:8]
        group['nonnull_count'] = group[
            ['profit', 'revenue', 'gross_margin', 'net_margin']
        ].notna().sum(axis=1)
        group = group.sort_values(['end_date', 'nonnull_count', 'report_date'])
        group = group.drop_duplicates(subset=['period_year', 'period_suffix'], keep='last')

        period_rows = {
            (int(row.period_year), row.period_suffix): row
            for row in group.itertuples(index=False)
        }

        quarter_values = {}
        for key, row in period_rows.items():
            quarter_values[key] = self._financial_quarter_values(row, period_rows)

        updates = []
        for key, row in period_rows.items():
            current = quarter_values.get(key, {})
            previous = self._previous_quarter_key(key)
            same_quarter_last_year = (key[0] - 1, key[1])
            previous_values = quarter_values.get(previous, {})
            yoy_values = quarter_values.get(same_quarter_last_year, {})

            updates.append({
                'id': row.id,
                'quarter_profit': current.get('profit'),
                'quarter_revenue': current.get('revenue'),
                'quarter_deducted_profit': current.get('deducted_profit'),
                'quarter_operating_cash_flow': current.get('operating_cash_flow'),
                'quarter_gross_margin': current.get('gross_margin'),
                'quarter_net_margin': current.get('net_margin'),
                'quarter_ocf_to_profit': current.get('ocf_to_profit'),
                'quarter_sales_expense_rate': current.get('sales_expense_rate'),
                'quarter_admin_expense_rate': current.get('admin_expense_rate'),
                'quarter_rd_expense_rate': current.get('rd_expense_rate'),
                'profit_yoy': self._pct_change(current.get('profit'), yoy_values.get('profit')),
                'profit_qoq': self._pct_change(current.get('profit'), previous_values.get('profit')),
                'revenue_yoy': self._pct_change(current.get('revenue'), yoy_values.get('revenue')),
                'revenue_qoq': self._pct_change(current.get('revenue'), previous_values.get('revenue')),
                'deducted_profit_yoy': self._pct_change(
                    current.get('deducted_profit'), yoy_values.get('deducted_profit')
                ),
                'deducted_profit_qoq': self._pct_change(
                    current.get('deducted_profit'), previous_values.get('deducted_profit')
                ),
                'operating_cash_flow_yoy': self._pct_change(
                    current.get('operating_cash_flow'), yoy_values.get('operating_cash_flow')
                ),
                'operating_cash_flow_qoq': self._pct_change(
                    current.get('operating_cash_flow'), previous_values.get('operating_cash_flow')
                ),
                'gross_margin_yoy': self._point_change(
                    current.get('gross_margin'), yoy_values.get('gross_margin')
                ),
                'gross_margin_qoq': self._point_change(
                    current.get('gross_margin'), previous_values.get('gross_margin')
                ),
                'net_margin_yoy': self._point_change(
                    current.get('net_margin'), yoy_values.get('net_margin')
                ),
                'net_margin_qoq': self._point_change(
                    current.get('net_margin'), previous_values.get('net_margin')
                ),
                'ocf_to_profit_yoy': self._point_change(
                    current.get('ocf_to_profit'), yoy_values.get('ocf_to_profit')
                ),
                'ocf_to_profit_qoq': self._point_change(
                    current.get('ocf_to_profit'), previous_values.get('ocf_to_profit')
                ),
                'roe_yoy': self._point_change(row.roe, getattr(yoy_values.get('source_row'), 'roe', None)),
                'roe_qoq': self._point_change(row.roe, getattr(previous_values.get('source_row'), 'roe', None)),
                'roic_yoy': self._point_change(row.roic, getattr(yoy_values.get('source_row'), 'roic', None)),
                'roic_qoq': self._point_change(row.roic, getattr(previous_values.get('source_row'), 'roic', None)),
                'debt_to_assets_yoy': self._point_change(
                    row.debt_to_assets, getattr(yoy_values.get('source_row'), 'debt_to_assets', None)
                ),
                'debt_to_assets_qoq': self._point_change(
                    row.debt_to_assets, getattr(previous_values.get('source_row'), 'debt_to_assets', None)
                ),
                'sales_expense_rate_yoy': self._point_change(
                    current.get('sales_expense_rate'), yoy_values.get('sales_expense_rate')
                ),
                'sales_expense_rate_qoq': self._point_change(
                    current.get('sales_expense_rate'), previous_values.get('sales_expense_rate')
                ),
                'admin_expense_rate_yoy': self._point_change(
                    current.get('admin_expense_rate'), yoy_values.get('admin_expense_rate')
                ),
                'admin_expense_rate_qoq': self._point_change(
                    current.get('admin_expense_rate'), previous_values.get('admin_expense_rate')
                ),
                'rd_expense_rate_yoy': self._point_change(
                    current.get('rd_expense_rate'), yoy_values.get('rd_expense_rate')
                ),
                'rd_expense_rate_qoq': self._point_change(
                    current.get('rd_expense_rate'), previous_values.get('rd_expense_rate')
                ),
            })

        return updates

    def _financial_quarter_values(self, row, period_rows: dict) -> dict:
        year = int(row.period_year)
        suffix = row.period_suffix
        profit = self._number_or_none(row.profit)
        revenue = self._number_or_none(row.revenue)
        deducted_profit = self._number_or_none(getattr(row, 'deducted_profit', None))
        operating_cash_flow = self._number_or_none(getattr(row, 'operating_cash_flow', None))
        sales_expense = self._number_or_none(getattr(row, 'sales_expense', None))
        admin_expense = self._number_or_none(getattr(row, 'admin_expense', None))
        rd_expense = self._number_or_none(getattr(row, 'rd_expense', None))
        gross_margin = self._number_or_none(row.gross_margin)

        gross_profit = None
        if revenue is not None and gross_margin is not None:
            gross_profit = revenue * gross_margin / 100

        if suffix == '0331':
            quarter_profit = profit
            quarter_revenue = revenue
            quarter_deducted_profit = deducted_profit
            quarter_operating_cash_flow = operating_cash_flow
            quarter_sales_expense = sales_expense
            quarter_admin_expense = admin_expense
            quarter_rd_expense = rd_expense
            quarter_gross_profit = gross_profit
        elif suffix == '0630':
            q1 = period_rows.get((year, '0331'))
            quarter_profit = self._subtract(profit, self._number_or_none(getattr(q1, 'profit', None)))
            quarter_revenue = self._subtract(revenue, self._number_or_none(getattr(q1, 'revenue', None)))
            quarter_deducted_profit = self._subtract(
                deducted_profit, self._number_or_none(getattr(q1, 'deducted_profit', None))
            )
            quarter_operating_cash_flow = self._subtract(
                operating_cash_flow, self._number_or_none(getattr(q1, 'operating_cash_flow', None))
            )
            quarter_sales_expense = self._subtract(
                sales_expense, self._number_or_none(getattr(q1, 'sales_expense', None))
            )
            quarter_admin_expense = self._subtract(
                admin_expense, self._number_or_none(getattr(q1, 'admin_expense', None))
            )
            quarter_rd_expense = self._subtract(
                rd_expense, self._number_or_none(getattr(q1, 'rd_expense', None))
            )
            quarter_gross_profit = self._subtract(gross_profit, self._gross_profit_from_row(q1))
        elif suffix == '0930':
            h1 = period_rows.get((year, '0630'))
            quarter_profit = self._subtract(profit, self._number_or_none(getattr(h1, 'profit', None)))
            quarter_revenue = self._subtract(revenue, self._number_or_none(getattr(h1, 'revenue', None)))
            quarter_deducted_profit = self._subtract(
                deducted_profit, self._number_or_none(getattr(h1, 'deducted_profit', None))
            )
            quarter_operating_cash_flow = self._subtract(
                operating_cash_flow, self._number_or_none(getattr(h1, 'operating_cash_flow', None))
            )
            quarter_sales_expense = self._subtract(
                sales_expense, self._number_or_none(getattr(h1, 'sales_expense', None))
            )
            quarter_admin_expense = self._subtract(
                admin_expense, self._number_or_none(getattr(h1, 'admin_expense', None))
            )
            quarter_rd_expense = self._subtract(
                rd_expense, self._number_or_none(getattr(h1, 'rd_expense', None))
            )
            quarter_gross_profit = self._subtract(gross_profit, self._gross_profit_from_row(h1))
        elif suffix == '1231':
            q3 = period_rows.get((year, '0930'))
            quarter_profit = self._subtract(profit, self._number_or_none(getattr(q3, 'profit', None)))
            quarter_revenue = self._subtract(revenue, self._number_or_none(getattr(q3, 'revenue', None)))
            quarter_deducted_profit = self._subtract(
                deducted_profit, self._number_or_none(getattr(q3, 'deducted_profit', None))
            )
            quarter_operating_cash_flow = self._subtract(
                operating_cash_flow, self._number_or_none(getattr(q3, 'operating_cash_flow', None))
            )
            quarter_sales_expense = self._subtract(
                sales_expense, self._number_or_none(getattr(q3, 'sales_expense', None))
            )
            quarter_admin_expense = self._subtract(
                admin_expense, self._number_or_none(getattr(q3, 'admin_expense', None))
            )
            quarter_rd_expense = self._subtract(
                rd_expense, self._number_or_none(getattr(q3, 'rd_expense', None))
            )
            quarter_gross_profit = self._subtract(gross_profit, self._gross_profit_from_row(q3))
        else:
            quarter_profit = None
            quarter_revenue = None
            quarter_deducted_profit = None
            quarter_operating_cash_flow = None
            quarter_sales_expense = None
            quarter_admin_expense = None
            quarter_rd_expense = None
            quarter_gross_profit = None

        return {
            'profit': quarter_profit,
            'revenue': quarter_revenue,
            'deducted_profit': quarter_deducted_profit,
            'operating_cash_flow': quarter_operating_cash_flow,
            'gross_margin': self._ratio_percent(quarter_gross_profit, quarter_revenue),
            'net_margin': self._ratio_percent(quarter_profit, quarter_revenue),
            'ocf_to_profit': self._ratio_plain(quarter_operating_cash_flow, quarter_profit),
            'sales_expense_rate': self._ratio_percent(quarter_sales_expense, quarter_revenue),
            'admin_expense_rate': self._ratio_percent(quarter_admin_expense, quarter_revenue),
            'rd_expense_rate': self._ratio_percent(quarter_rd_expense, quarter_revenue),
            'source_row': row,
        }

    def _gross_profit_from_row(self, row) -> Optional[float]:
        if row is None:
            return None
        revenue = self._number_or_none(getattr(row, 'revenue', None))
        gross_margin = self._number_or_none(getattr(row, 'gross_margin', None))
        if revenue is None or gross_margin is None:
            return None
        return revenue * gross_margin / 100

    def _previous_quarter_key(self, key: Tuple[int, str]) -> Tuple[int, str]:
        year, suffix = key
        if suffix == '0331':
            return (year - 1, '1231')
        if suffix == '0630':
            return (year, '0331')
        if suffix == '0930':
            return (year, '0630')
        if suffix == '1231':
            return (year, '0930')
        return (year, suffix)

    def _number_or_none(self, value) -> Optional[float]:
        if value is None or pd.isna(value):
            return None
        return float(value)

    def _subtract(self, current, previous) -> Optional[float]:
        if current is None or previous is None:
            return None
        return current - previous

    def _ratio_percent(self, numerator, denominator) -> Optional[float]:
        if numerator is None or denominator in (None, 0):
            return None
        return numerator / denominator * 100

    def _ratio_plain(self, numerator, denominator) -> Optional[float]:
        if numerator is None or denominator in (None, 0):
            return None
        return numerator / denominator

    def _pct_change(self, current, previous) -> Optional[float]:
        current = self._number_or_none(current)
        previous = self._number_or_none(previous)
        if current is None or previous in (None, 0):
            return None
        return (current - previous) / abs(previous) * 100

    def _point_change(self, current, previous) -> Optional[float]:
        current = self._number_or_none(current)
        previous = self._number_or_none(previous)
        if current is None or previous is None:
            return None
        return current - previous

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

    def get_latest_adj_factor(self, ts_code: str) -> Optional[float]:
        """
        获取指定股票最新一条非空复权因子。

        Args:
            ts_code: 股票代码

        Returns:
            最新复权因子；如果无数据则返回 None
        """
        try:
            query = """
                SELECT adj_factor
                FROM daily_ohlcv
                WHERE ts_code = ?
                  AND adj_factor IS NOT NULL
                ORDER BY trade_date DESC
                LIMIT 1
            """
            cursor = self.conn.execute(query, (ts_code,))
            result = cursor.fetchone()
            return float(result[0]) if result and result[0] is not None else None
        except Exception as e:
            logger.error(f"查询最新复权因子失败 ({ts_code}): {e}")
            return None

    def rescale_qfq_history(
        self,
        ts_code: str,
        scale_ratio: float,
        before_trade_date: Optional[str] = None,
    ):
        """
        按比例回刷指定股票已有前复权价格。

        仅缩放价格字段，不改动 change/pct_chg 等涨跌幅字段；这些字段对等比缩放不敏感。

        Args:
            ts_code: 股票代码
            scale_ratio: 缩放比例
            before_trade_date: 仅处理该日期之前的数据（不含当日）
        """
        if scale_ratio is None or scale_ratio <= 0:
            logger.warning(f"非法复权回刷比例，跳过 ({ts_code}): {scale_ratio}")
            return

        params = [scale_ratio, scale_ratio, scale_ratio, scale_ratio, scale_ratio, ts_code]
        query = """
            UPDATE daily_ohlcv
            SET open = open * ?,
                high = high * ?,
                low = low * ?,
                close = close * ?,
                pre_close = pre_close * ?
            WHERE ts_code = ?
        """
        if before_trade_date:
            query += " AND trade_date < ?"
            params.append(before_trade_date)

        try:
            cursor = self.conn.execute(query, params)
            self.conn.commit()
            logger.info(
                f"成功回刷 {ts_code} 前复权历史 {cursor.rowcount} 条，比例 {scale_ratio:.8f}"
            )
        except Exception as e:
            logger.error(f"回刷前复权历史失败 ({ts_code}): {e}")
            self.conn.rollback()
            raise

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
            cursor.execute("DELETE FROM financial_metrics WHERE ts_code = ?", (ts_code,))
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

            # 财务指标记录数
            cursor = self.conn.execute("SELECT COUNT(*) FROM financial_metrics")
            stats['financial_metrics_records'] = cursor.fetchone()[0]

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
