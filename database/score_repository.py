"""
打分数据仓库
提供滚动窗口打分数据的存储和查询功能
"""

import sqlite3
import pandas as pd
import os
from datetime import datetime
from typing import Optional, List, Tuple
import logging
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScoreRepository:
    """打分数据仓库类"""

    def __init__(self, db_path: str = None):
        """
        初始化数据仓库

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

    def _connect(self):
        """建立数据库连接"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            logger.debug(f"打分数据仓库连接成功: {self.db_path}")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise

    def save_scores(self, ts_code: str, df_scores: pd.DataFrame):
        """
        保存打分数据（覆盖模式）

        Args:
            ts_code: 股票代码
            df_scores: 包含打分数据的DataFrame
        """
        if df_scores is None or df_scores.empty:
            logger.warning(f"数据为空，跳过保存 ({ts_code})")
            return

        try:
            # 先删除该股票的所有旧数据
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM rolling_scores WHERE ts_code = ?", (ts_code,))
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(f"已删除 {ts_code} 的 {deleted_count} 条旧打分记录")

            # 准备数据
            df_save = df_scores.copy()
            df_save['ts_code'] = ts_code
            df_save['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 确保列名匹配数据库字段
            column_mapping = {
                'date': 'trade_date',
                'total_score': 'total_score',
                'trend_score': 'trend_score',
                'momentum_score': 'momentum_score',
                'volatility_score': 'volatility_score',
                'volume_score': 'volume_score',
                'pattern_score': 'pattern_score',
                'score_level': 'score_level',
                'close': 'close',
                'next_date': 'next_date',
                'change_pct': 'change_pct',
                'rsi': 'rsi',
                'mfi': 'mfi',
                'k': 'k',
                'd': 'd',
                'j': 'j',
                'cci': 'cci',
                'atr': 'atr',
                'volume_ratio': 'volume_ratio',
                'score_details': 'score_details',
                'signals': 'signals'
            }

            # 只保留存在的列
            existing_columns = {k: v for k, v in column_mapping.items() if k in df_save.columns}
            df_save = df_save.rename(columns=existing_columns)

            # 确保必需字段存在
            required_fields = ['ts_code', 'trade_date', 'total_score']
            missing_fields = [f for f in required_fields if f not in df_save.columns]
            if missing_fields:
                logger.error(f"缺少必需字段: {missing_fields}")
                return

            # 选择要保存的列
            db_columns = [
                'ts_code', 'trade_date', 'close', 'next_date', 'change_pct',
                'total_score', 'trend_score', 'momentum_score', 'volatility_score',
                'volume_score', 'pattern_score', 'score_level',
                'rsi', 'mfi', 'k', 'd', 'j', 'cci', 'atr', 'volume_ratio',
                'score_details', 'signals', 'updated_at'
            ]

            # 只保留存在的列
            columns_to_save = [col for col in db_columns if col in df_save.columns]
            df_to_insert = df_save[columns_to_save]

            # 插入数据
            df_to_insert.to_sql(
                'rolling_scores',
                self.conn,
                if_exists='append',
                index=False,
                method='multi'
            )
            self.conn.commit()
            logger.info(f"✓ 已保存 {len(df_to_insert)} 条打分记录到数据库 ({ts_code})")

        except Exception as e:
            logger.error(f"保存打分数据失败 ({ts_code}): {e}")
            self.conn.rollback()
            raise

    def load_scores(self, ts_code: str, start_date: str = None,
                    end_date: str = None) -> Optional[pd.DataFrame]:
        """
        读取打分数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期 YYYYMMDD 或 YYYY-MM-DD
            end_date: 结束日期 YYYYMMDD 或 YYYY-MM-DD

        Returns:
            包含打分数据的DataFrame，如果无数据则返回None
        """
        # 统一日期格式为YYYYMMDD
        if start_date and '-' in start_date:
            start_date = start_date.replace('-', '')
        if end_date and '-' in end_date:
            end_date = end_date.replace('-', '')

        query = "SELECT * FROM rolling_scores WHERE ts_code = ?"
        params = [ts_code]

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date DESC"

        try:
            df = pd.read_sql_query(query, self.conn, params=params)

            if df.empty:
                logger.debug(f"数据库中无打分数据 ({ts_code})")
                return None

            # 重命名列以匹配原始格式
            column_mapping = {
                'trade_date': 'date',
                'ts_code': 'ts_code',
                'total_score': 'total_score',
                'trend_score': 'trend_score',
                'momentum_score': 'momentum_score',
                'volatility_score': 'volatility_score',
                'volume_score': 'volume_score',
                'pattern_score': 'pattern_score',
                'score_level': 'score_level',
                'close': 'close',
                'next_date': 'next_date',
                'change_pct': 'change_pct',
                'rsi': 'rsi',
                'mfi': 'mfi',
                'k': 'k',
                'd': 'd',
                'j': 'j',
                'cci': 'cci',
                'atr': 'atr',
                'volume_ratio': 'volume_ratio',
                'score_details': 'score_details',
                'signals': 'signals'
            }

            df = df.rename(columns=column_mapping)

            # 删除不需要的列
            columns_to_drop = ['id', 'updated_at']
            df = df.drop(columns=[col for col in columns_to_drop if col in df.columns])

            logger.info(f"✓ 从数据库加载打分数据: {len(df)} 条记录 ({ts_code})")
            return df

        except Exception as e:
            logger.error(f"读取打分数据失败 ({ts_code}): {e}")
            return None

    def get_available_dates(self, ts_code: str) -> List[str]:
        """
        获取该股票已有打分的日期列表

        Args:
            ts_code: 股票代码

        Returns:
            日期列表 (YYYYMMDD格式)
        """
        try:
            query = """
                SELECT DISTINCT trade_date
                FROM rolling_scores
                WHERE ts_code = ?
                ORDER BY trade_date DESC
            """
            cursor = self.conn.execute(query, (ts_code,))
            dates = [row[0] for row in cursor.fetchall()]
            return dates
        except Exception as e:
            logger.error(f"查询日期列表失败 ({ts_code}): {e}")
            return []

    def get_score_info(self, ts_code: str) -> Optional[dict]:
        """
        获取该股票的打分数据信息

        Args:
            ts_code: 股票代码

        Returns:
            包含统计信息的字典，如果无数据则返回None
        """
        try:
            query = """
                SELECT
                    COUNT(*) as count,
                    MIN(trade_date) as min_date,
                    MAX(trade_date) as max_date,
                    AVG(total_score) as avg_score,
                    MAX(updated_at) as last_update
                FROM rolling_scores
                WHERE ts_code = ?
            """
            cursor = self.conn.execute(query, (ts_code,))
            row = cursor.fetchone()

            if row and row[0] > 0:
                return {
                    'ts_code': ts_code,
                    'record_count': row[0],
                    'date_range': (row[1], row[2]),
                    'avg_score': round(row[3], 2) if row[3] else None,
                    'last_update': row[4]
                }
            else:
                return None

        except Exception as e:
            logger.error(f"查询打分信息失败 ({ts_code}): {e}")
            return None

    def delete_scores(self, ts_code: str):
        """
        删除指定股票的所有打分数据

        Args:
            ts_code: 股票代码
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM rolling_scores WHERE ts_code = ?", (ts_code,))
            deleted_count = cursor.rowcount
            self.conn.commit()
            logger.info(f"成功删除 {ts_code} 的 {deleted_count} 条打分记录")
        except Exception as e:
            logger.error(f"删除打分数据失败 ({ts_code}): {e}")
            self.conn.rollback()
            raise

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.debug("打分数据仓库连接已关闭")

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器时关闭连接"""
        self.close()


if __name__ == '__main__':
    # 测试代码
    repo = ScoreRepository()

    # 测试查询
    test_code = '000001.SZ'
    info = repo.get_score_info(test_code)

    if info:
        print(f"\n=== {test_code} 打分数据信息 ===")
        print(f"记录数量: {info['record_count']}")
        print(f"日期范围: {info['date_range']}")
        print(f"平均得分: {info['avg_score']}")
        print(f"最后更新: {info['last_update']}")
    else:
        print(f"\n{test_code} 无打分数据")

    repo.close()
