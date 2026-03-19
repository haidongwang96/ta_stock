import os
import sqlite3
import tempfile
import unittest

import pandas as pd

from database.db_manager import StockDatabase


class DbManagerOptimizationTests(unittest.TestCase):
    def _make_temp_db_path(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        return path

    def test_init_migrates_stock_basic_to_primary_key_schema(self):
        db_path = self._make_temp_db_path()
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE stock_basic (
                    ts_code TEXT,
                    symbol TEXT,
                    name TEXT,
                    area TEXT,
                    industry TEXT,
                    market TEXT,
                    list_date TEXT,
                    update_time TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO stock_basic (
                    ts_code, symbol, name, area, industry, market, list_date, update_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("000001.SZ", "000001", "平安银行", "深圳", "银行", "主板", "19910403", "2026-03-19 10:00:00"),
            )
            conn.commit()
            conn.close()

            db = StockDatabase(db_path)
            db.close()

            conn = sqlite3.connect(db_path)
            table_info = conn.execute("PRAGMA table_info(stock_basic)").fetchall()
            rows = conn.execute("SELECT COUNT(*), COUNT(DISTINCT ts_code) FROM stock_basic").fetchone()
            conn.close()

            ts_code_row = next(row for row in table_info if row[1] == "ts_code")
            self.assertEqual(ts_code_row[5], 1)
            self.assertEqual(rows, (1, 1))
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_insert_stock_basic_preserves_primary_key_schema(self):
        db_path = self._make_temp_db_path()
        try:
            db = StockDatabase(db_path)
            stock_info = pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "symbol": "000001",
                        "name": "平安银行",
                        "area": "深圳",
                        "industry": "银行",
                        "market": "主板",
                        "list_date": "19910403",
                    }
                ]
            )
            db.insert_stock_basic(stock_info)
            db.close()

            conn = sqlite3.connect(db_path)
            table_info = conn.execute("PRAGMA table_info(stock_basic)").fetchall()
            rows = conn.execute("SELECT COUNT(*), COUNT(DISTINCT ts_code) FROM stock_basic").fetchone()
            conn.close()

            ts_code_row = next(row for row in table_info if row[1] == "ts_code")
            self.assertEqual(ts_code_row[5], 1)
            self.assertEqual(rows, (1, 1))
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_init_enables_wal_and_avoids_duplicate_composite_indexes(self):
        db_path = self._make_temp_db_path()
        try:
            db = StockDatabase(db_path)
            journal_mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
            synchronous = db.conn.execute("PRAGMA synchronous").fetchone()[0]
            db.close()

            conn = sqlite3.connect(db_path)
            index_names = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'index'
                      AND tbl_name IN ('daily_ohlcv', 'daily_indicators')
                    ORDER BY name
                    """
                ).fetchall()
            ]
            conn.close()

            self.assertEqual(journal_mode.lower(), "wal")
            self.assertEqual(synchronous, 1)
            self.assertNotIn("idx_daily_ohlcv_code_date", index_names)
            self.assertNotIn("idx_daily_indicators_code_date", index_names)
            self.assertIn("idx_daily_ohlcv_date", index_names)
            self.assertIn("idx_daily_indicators_date", index_names)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


if __name__ == "__main__":
    unittest.main()
