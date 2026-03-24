import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

sys.modules.setdefault("tushare", types.SimpleNamespace())
sys.modules.setdefault("pandas_ta", types.SimpleNamespace())

from scripts.stock_analysis import analyze_single_stock, save_analysis_results_to_db
from analysis.year_stats import calculate_year_stats


class _DummyAnalyzer:
    def __init__(self, use_local_db=False, suppress_logs=False):
        self.use_local_db = use_local_db
        self.suppress_logs = suppress_logs

    def fetch_data(self, stock_code, start_date, end_date):
        if start_date == "20260101":
            return pd.DataFrame(
                [
                    {"trade_date": pd.Timestamp("2026-01-02"), "High": 10.5, "Close": 10.0},
                    {"trade_date": pd.Timestamp("2026-02-03"), "High": 12.0, "Close": 11.2},
                    {"trade_date": pd.Timestamp("2026-03-18"), "High": 11.0, "Close": 10.8},
                ]
            )

        records = []
        trade_dates = pd.date_range("2026-02-26", periods=21, freq="D")
        for idx, trade_date in enumerate(trade_dates, start=1):
            record = {
                "trade_date": trade_date,
                "Close": float(idx),
            }
            if idx == len(trade_dates):
                record.update(
                    {
                        "RSI": 60.0,
                        "MFI": 55.0,
                        "CCI": 100.0,
                        "K": 70.0,
                        "D": 65.0,
                        "J": 80.0,
                        "MACD_DIF": 0.1234,
                        "MACD_DEA": 0.1001,
                        "MACD_Histogram": 0.0466,
                        "Volume_Ratio": 1.4,
                        "VWAP": 20.6,
                        "ATR": 0.5,
                    }
                )
            records.append(record)

        return pd.DataFrame(records)

    def calculate_indicators(self, df):
        return df

    def detect_patterns(self, df):
        return {"signals": ["测试信号"]}


class StockAnalysisYearStatsTests(unittest.TestCase):
    def test_calculate_year_stats_returns_expected_snapshot(self):
        df = pd.DataFrame(
            [
                {"trade_date": "20260102", "high": 10.5, "close": 10.0},
                {"trade_date": "20260203", "high": 12.0, "close": 11.2},
                {"trade_date": "20260318", "high": 11.0, "close": 10.8},
            ]
        )

        result = calculate_year_stats(df)

        self.assertEqual(
            result,
            {
                "current_price": 10.8,
                "year_high": 12.0,
                "year_high_date": "20260203",
                "year_high_close": 11.2,
                "drop_from_year_high_pct": 10.0,
                "latest_date": "20260318",
            },
        )

    def test_analyze_single_stock_includes_year_stats_by_default(self):
        with patch("scripts.stock_analysis.StockAnalyzer", _DummyAnalyzer):
            result = analyze_single_stock(
                ("000001.SZ", "平安银行", "20260301", "20260318", True, True)
            )

        self.assertIn("year_stats", result)
        self.assertEqual(result["year_stats"]["year_high"], 12.0)
        self.assertEqual(result["year_stats"]["drop_from_year_high_pct"], 10.0)
        self.assertEqual(result["pct_5d"], 31.25)
        self.assertEqual(result["pct_10d"], 90.91)
        self.assertEqual(result["pct_20d"], 2000.0)

    def test_analyze_single_stock_can_skip_year_stats(self):
        with patch("scripts.stock_analysis.StockAnalyzer", _DummyAnalyzer):
            result = analyze_single_stock(
                ("000001.SZ", "平安银行", "20260301", "20260318", True, False)
            )

        self.assertNotIn("year_stats", result)
        self.assertEqual(result["pct_5d"], 31.25)
        self.assertEqual(result["pct_10d"], 90.91)
        self.assertEqual(result["pct_20d"], 2000.0)

    def test_save_analysis_results_to_db_defaults_to_local_db(self):
        results = [{"code": "000001.SZ", "date": "20260318", "patterns": {"signals": []}}]

        class _FakeDB:
            def __init__(self):
                self.saved = None
                self.closed = False

            def save_pattern_analysis_results(self, saved_results, source):
                self.saved = (saved_results, source)

            def close(self):
                self.closed = True

        fake_db = _FakeDB()
        with patch("scripts.stock_analysis.StockDatabase", return_value=fake_db):
            save_analysis_results_to_db(results)

        self.assertEqual(fake_db.saved, (results, "local_db"))
        self.assertTrue(fake_db.closed)


if __name__ == "__main__":
    unittest.main()
