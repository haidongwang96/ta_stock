import json
import os
import tempfile
import unittest

from database.db_manager import StockDatabase


class PatternAnalysisStorageTests(unittest.TestCase):
    def _make_temp_db_path(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        return path

    def test_init_creates_pattern_analysis_table(self):
        db_path = self._make_temp_db_path()
        try:
            db = StockDatabase(db_path)
            tables = {
                row[0]
                for row in db.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            indexes = {
                row[0]
                for row in db.conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type='index' AND tbl_name='daily_pattern_analysis'
                    """
                ).fetchall()
            }
            columns = {
                row[1]
                for row in db.conn.execute(
                    "PRAGMA table_info(daily_pattern_analysis)"
                ).fetchall()
            }
            db.close()

            self.assertIn("daily_pattern_analysis", tables)
            self.assertIn("idx_daily_pattern_analysis_date", indexes)
            self.assertIn("idx_daily_pattern_analysis_code", indexes)
            self.assertIn("pct_5d", columns)
            self.assertIn("pct_10d", columns)
            self.assertIn("pct_20d", columns)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_save_pattern_analysis_results_persists_json_payload(self):
        db = StockDatabase(":memory:")
        try:
            results = [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "date": "20260318",
                    "close": 10.8,
                    "change_pct": 1.5,
                    "pct_5d": 3.5,
                    "pct_10d": 6.8,
                    "pct_20d": 12.4,
                    "indicators": {"rsi": 60.0, "atr": 0.5},
                    "patterns": {"signals": ["MACD金叉"]},
                    "year_stats": {"year_high": 12.0},
                }
            ]

            db.save_pattern_analysis_results(results, source="local_db")
            saved = db.get_pattern_analysis("000001.SZ")

            self.assertEqual(len(saved), 1)
            self.assertEqual(saved.loc[0, "ts_code"], "000001.SZ")
            self.assertEqual(saved.loc[0, "trade_date"], "20260318")
            self.assertEqual(saved.loc[0, "close"], 10.8)
            self.assertEqual(saved.loc[0, "change_pct"], 1.5)
            self.assertEqual(saved.loc[0, "pct_5d"], 3.5)
            self.assertEqual(saved.loc[0, "pct_10d"], 6.8)
            self.assertEqual(saved.loc[0, "pct_20d"], 12.4)
            self.assertEqual(saved.loc[0, "source"], "local_db")

            analysis_payload = json.loads(saved.loc[0, "analysis_payload"])
            self.assertEqual(analysis_payload["patterns"]["signals"], ["MACD金叉"])
            self.assertEqual(analysis_payload["pct_5d"], 3.5)
            self.assertEqual(analysis_payload["pct_10d"], 6.8)
            self.assertEqual(analysis_payload["pct_20d"], 12.4)
            self.assertEqual(
                json.loads(saved.loc[0, "indicators_json"]),
                {"rsi": 60.0, "atr": 0.5},
            )
            self.assertEqual(
                json.loads(saved.loc[0, "year_stats_json"]),
                {"year_high": 12.0},
            )
        finally:
            db.close()

    def test_save_pattern_analysis_results_replaces_same_stock_same_day(self):
        db = StockDatabase(":memory:")
        try:
            initial = [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "date": "20260318",
                    "close": 10.8,
                    "change_pct": 1.5,
                    "pct_5d": 3.5,
                    "pct_10d": 6.8,
                    "pct_20d": 12.4,
                    "indicators": {"rsi": 60.0},
                    "patterns": {"signals": ["旧信号"]},
                }
            ]
            updated = [
                {
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "date": "20260318",
                    "close": 11.0,
                    "change_pct": 2.2,
                    "pct_5d": 4.5,
                    "pct_10d": 7.8,
                    "pct_20d": 13.4,
                    "indicators": {"rsi": 65.0},
                    "patterns": {"signals": ["新信号"]},
                }
            ]

            db.save_pattern_analysis_results(initial, source="local_db")
            db.save_pattern_analysis_results(updated, source="local_db")
            saved = db.get_pattern_analysis("000001.SZ")

            self.assertEqual(len(saved), 1)
            self.assertEqual(saved.loc[0, "close"], 11.0)
            self.assertEqual(saved.loc[0, "pct_5d"], 4.5)
            self.assertEqual(saved.loc[0, "pct_10d"], 7.8)
            self.assertEqual(saved.loc[0, "pct_20d"], 13.4)
            self.assertEqual(json.loads(saved.loc[0, "patterns_json"])["signals"], ["新信号"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
