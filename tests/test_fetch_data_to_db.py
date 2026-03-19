import sys
import types
import unittest
from unittest.mock import Mock, patch

import pandas as pd

sys.modules.setdefault("tushare", types.SimpleNamespace())
sys.modules.setdefault("pandas_ta", types.SimpleNamespace())

from database.db_manager import StockDatabase
from database.fetch_data_to_db import DataFetcher


DAILY_BASIC_FIELDS = [
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
    "total_mv",
    "circ_mv",
]


class _FixedDateTime:
    @classmethod
    def now(cls):
        from datetime import datetime
        return datetime(2026, 3, 18, 12, 0, 0)

    @classmethod
    def strptime(cls, value, fmt):
        from datetime import datetime
        return datetime.strptime(value, fmt)


class _FakeDB:
    def __init__(self, latest_date, missing_daily_basic_range=None):
        self.latest_date = latest_date
        self.missing_daily_basic_range = missing_daily_basic_range

    def get_latest_date(self, ts_code=None):
        return self.latest_date

    def get_missing_daily_basic_range(self, ts_code):
        return self.missing_daily_basic_range

    def get_data_statistics(self):
        return {"ohlcv_records": 0}


class FetchDataToDbTests(unittest.TestCase):
    def _build_fetcher(self, latest_date, missing_daily_basic_range=None):
        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher.db = _FakeDB(
            latest_date=latest_date,
            missing_daily_basic_range=missing_daily_basic_range,
        )
        fetcher.process_stock = Mock(return_value=True)
        fetcher.is_trade_date = Mock(return_value=True)
        return fetcher

    def test_fetch_daily_data_merges_all_daily_basic_fields(self):
        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher.pro = Mock()
        fetcher.pro.daily.return_value = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260318",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.2,
                    "pre_close": 10.0,
                    "change": 0.2,
                    "pct_chg": 2.0,
                    "vol": 1000,
                    "amount": 2000,
                }
            ]
        )
        fetcher.pro.daily_basic.return_value = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260318",
                    "turnover_rate": 1.1,
                    "turnover_rate_f": 1.0,
                    "volume_ratio": 1.2,
                    "pe": 12.0,
                    "pe_ttm": 11.5,
                    "pb": 1.8,
                    "ps": 2.1,
                    "ps_ttm": 2.0,
                    "dv_ratio": 0.8,
                    "dv_ttm": 0.7,
                    "total_share": 100000,
                    "float_share": 80000,
                    "free_share": 60000,
                    "total_mv": 500000,
                    "circ_mv": 400000,
                }
            ]
        )

        df = fetcher.fetch_daily_data("000001.SZ", "20260301", "20260318")

        self.assertIsNotNone(df)
        for field in DAILY_BASIC_FIELDS:
            self.assertIn(field, df.columns)

    def test_update_reprocesses_when_daily_basic_fields_have_gaps(self):
        fetcher = self._build_fetcher(
            latest_date="20260318",
            missing_daily_basic_range=("20260310", "20260312"),
        )

        with patch("database.fetch_data_to_db.datetime", _FixedDateTime), patch(
            "database.fetch_data_to_db.time.sleep"
        ):
            fetcher.update_database(stock_codes=["000001.SZ"], incremental=True)

        fetcher.process_stock.assert_called_once_with(
            "000001.SZ", "20260310", "20260318", replace=True
        )

    def test_update_skips_when_latest_date_is_current_and_daily_basic_fields_are_complete(self):
        fetcher = self._build_fetcher(latest_date="20260318", missing_daily_basic_range=None)

        with patch("database.fetch_data_to_db.datetime", _FixedDateTime), patch(
            "database.fetch_data_to_db.time.sleep"
        ):
            fetcher.update_database(stock_codes=["000001.SZ"], incremental=True)

        fetcher.process_stock.assert_not_called()

    def test_missing_daily_basic_range_ignores_optional_null_fields(self):
        db = StockDatabase(":memory:")
        try:
            row = pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": "20260318",
                        "open": 10.0,
                        "high": 10.5,
                        "low": 9.8,
                        "close": 10.2,
                        "pre_close": 10.0,
                        "change": 0.2,
                        "pct_chg": 2.0,
                        "vol": 1000,
                        "amount": 2000,
                        "turnover_rate": 1.1,
                        "turnover_rate_f": 1.0,
                        "volume_ratio": 1.2,
                        "pe": None,
                        "pe_ttm": None,
                        "pb": None,
                        "ps": None,
                        "ps_ttm": None,
                        "dv_ratio": None,
                        "dv_ttm": None,
                        "total_share": 100000,
                        "float_share": 80000,
                        "free_share": 60000,
                        "total_mv": 500000,
                        "circ_mv": 400000,
                    }
                ]
            )
            db.insert_daily_ohlcv(row, replace=False)

            self.assertEqual(
                db.get_missing_daily_basic_range("000001.SZ"),
                (None, None),
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
