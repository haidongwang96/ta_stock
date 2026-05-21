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

    def test_financial_metrics_table_supports_latest_report_query(self):
        db_path = self._make_temp_db_path()
        try:
            db = StockDatabase(db_path)
            db.insert_financial_metrics(
                pd.DataFrame(
                    [
                        {
                            "ts_code": "000001.SZ",
                            "report_date": "20251030",
                            "end_date": "20250930",
                            "period_type": "Q3",
                            "profit": 100.0,
                            "revenue": 1000.0,
                            "gross_margin": 42.5,
                            "net_margin": 10.0,
                        },
                        {
                            "ts_code": "000001.SZ",
                            "report_date": "20260430",
                            "end_date": "20260331",
                            "period_type": "Q1",
                            "profit": 120.0,
                            "revenue": 1100.0,
                            "gross_margin": 43.5,
                            "net_margin": 10.9,
                        },
                    ]
                )
            )

            latest = db.get_latest_financial_metrics("000001.SZ")
            stats = db.get_data_statistics()
            db.close()

            self.assertEqual(len(latest), 1)
            self.assertEqual(latest.iloc[0]["report_date"], "20260430")
            self.assertEqual(latest.iloc[0]["period_type"], "Q1")
            self.assertEqual(stats["financial_metrics_records"], 2)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_financial_metrics_replace_handles_nullable_period_keys(self):
        db_path = self._make_temp_db_path()
        try:
            db = StockDatabase(db_path)
            first = pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "report_date": "20260430",
                        "profit": 100.0,
                        "revenue": 1000.0,
                    }
                ]
            )
            second = pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "report_date": "20260430",
                        "profit": 120.0,
                        "revenue": 1100.0,
                    }
                ]
            )

            db.insert_financial_metrics(first)
            db.insert_financial_metrics(second, replace=True)
            rows = db.get_financial_metrics("000001.SZ")
            db.close()

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows.iloc[0]["profit"], 120.0)
            self.assertEqual(rows.iloc[0]["revenue"], 1100.0)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_financial_growth_metrics_use_single_quarter_values(self):
        db_path = self._make_temp_db_path()
        try:
            db = StockDatabase(db_path)
            db.insert_financial_metrics(
                pd.DataFrame(
                    [
                        {
                            "ts_code": "000001.SZ",
                            "report_date": "20250430",
                            "end_date": "20250331",
                            "period_type": "Q1",
                            "profit": 100.0,
                            "revenue": 1000.0,
                            "deducted_profit": 80.0,
                            "operating_cash_flow": 120.0,
                            "sales_expense": 20.0,
                            "admin_expense": 30.0,
                            "rd_expense": 40.0,
                            "gross_margin": 40.0,
                            "net_margin": 10.0,
                        },
                        {
                            "ts_code": "000001.SZ",
                            "report_date": "20250830",
                            "end_date": "20250630",
                            "period_type": "H1",
                            "profit": 250.0,
                            "revenue": 2300.0,
                            "deducted_profit": 200.0,
                            "operating_cash_flow": 330.0,
                            "sales_expense": 50.0,
                            "admin_expense": 70.0,
                            "rd_expense": 100.0,
                            "gross_margin": 42.0,
                            "net_margin": 10.87,
                        },
                        {
                            "ts_code": "000001.SZ",
                            "report_date": "20251030",
                            "end_date": "20250930",
                            "period_type": "Q3",
                            "profit": 450.0,
                            "revenue": 3900.0,
                            "deducted_profit": 350.0,
                            "operating_cash_flow": 490.0,
                            "sales_expense": 90.0,
                            "admin_expense": 120.0,
                            "rd_expense": 180.0,
                            "gross_margin": 43.0,
                            "net_margin": 11.54,
                        },
                        {
                            "ts_code": "000001.SZ",
                            "report_date": "20260430",
                            "end_date": "20260331",
                            "period_type": "Q1",
                            "profit": 120.0,
                            "revenue": 1100.0,
                            "deducted_profit": 96.0,
                            "operating_cash_flow": 132.0,
                            "sales_expense": 22.0,
                            "admin_expense": 33.0,
                            "rd_expense": 44.0,
                            "gross_margin": 44.0,
                            "net_margin": 10.91,
                        },
                    ]
                )
            )

            db.update_financial_growth_metrics(["000001.SZ"])
            rows = db.get_financial_metrics("000001.SZ")
            db.close()

            h1 = rows[rows["end_date"] == "20250630"].iloc[0]
            q1_2026 = rows[rows["end_date"] == "20260331"].iloc[0]

            self.assertEqual(h1["quarter_profit"], 150.0)
            self.assertEqual(h1["quarter_revenue"], 1300.0)
            self.assertEqual(h1["quarter_deducted_profit"], 120.0)
            self.assertEqual(h1["quarter_operating_cash_flow"], 210.0)
            self.assertAlmostEqual(h1["quarter_ocf_to_profit"], 1.4)
            self.assertAlmostEqual(h1["quarter_rd_expense_rate"], 60.0 / 1300.0 * 100)
            self.assertAlmostEqual(h1["profit_qoq"], 50.0)
            self.assertAlmostEqual(h1["revenue_qoq"], 30.0)
            self.assertAlmostEqual(q1_2026["profit_yoy"], 20.0)
            self.assertAlmostEqual(q1_2026["revenue_yoy"], 10.0)
            self.assertAlmostEqual(q1_2026["deducted_profit_yoy"], 20.0)
            self.assertAlmostEqual(q1_2026["operating_cash_flow_yoy"], 10.0)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

if __name__ == "__main__":
    unittest.main()
