import sys
import types
import unittest
from unittest.mock import Mock, patch

import pandas as pd

sys.modules.setdefault("tushare", types.SimpleNamespace())
sys.modules.setdefault("pandas_ta", types.SimpleNamespace())

import database.fetch_data_to_db as fetch_data_to_db_module
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
    def __init__(self, latest_date, missing_daily_basic_range=None, stock_codes=None):
        self.latest_date = latest_date
        self.missing_daily_basic_range = missing_daily_basic_range
        self.stock_codes = stock_codes or ["000001.SZ"]

    def get_latest_date(self, ts_code=None):
        return self.latest_date

    def get_missing_daily_basic_range(self, ts_code):
        return self.missing_daily_basic_range

    def get_stock_list(self):
        return pd.DataFrame({"ts_code": self.stock_codes})

    def get_data_statistics(self):
        return {"ohlcv_records": 0}


class FetchDataToDbTests(unittest.TestCase):
    def _build_fetcher(self, latest_date, missing_daily_basic_range=None, stock_codes=None):
        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher.db = _FakeDB(
            latest_date=latest_date,
            missing_daily_basic_range=missing_daily_basic_range,
            stock_codes=stock_codes,
        )
        fetcher.process_stock = Mock(return_value=True)
        fetcher.process_trade_date = Mock(return_value=True)
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

    def test_fetch_daily_data_applies_local_qfq_from_adj_factor(self):
        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher.pro = Mock()
        fetcher.pro.daily.return_value = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260317",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.0,
                    "pre_close": 9.5,
                    "change": 0.5,
                    "pct_chg": 5.0,
                    "vol": 1000,
                    "amount": 2000,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260318",
                    "open": 20.0,
                    "high": 22.0,
                    "low": 19.0,
                    "close": 20.0,
                    "pre_close": 19.0,
                    "change": 1.0,
                    "pct_chg": 5.0,
                    "vol": 1200,
                    "amount": 2400,
                },
            ]
        )
        fetcher.pro.daily_basic.return_value = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20260317"},
                {"ts_code": "000001.SZ", "trade_date": "20260318"},
            ]
        )
        fetcher.pro.adj_factor.return_value = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20260317", "adj_factor": 1.0},
                {"ts_code": "000001.SZ", "trade_date": "20260318", "adj_factor": 2.0},
            ]
        )

        df = fetcher.fetch_daily_data("000001.SZ", "20260317", "20260318")

        self.assertEqual(df.loc[0, "open"], 5.0)
        self.assertEqual(df.loc[0, "close"], 5.0)
        self.assertEqual(df.loc[1, "open"], 20.0)
        self.assertEqual(df.loc[1, "adj_factor"], 2.0)

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

    def test_update_uses_trade_date_batches_for_full_universe_incremental_update(self):
        fetcher = self._build_fetcher(latest_date="20260316", stock_codes=["000001.SZ", "000002.SZ"])
        fetcher.get_open_trade_dates = Mock(return_value=["20260317", "20260318"])

        with patch("database.fetch_data_to_db.datetime", _FixedDateTime), patch(
            "database.fetch_data_to_db.time.sleep"
        ):
            fetcher.update_database(stock_codes=None, incremental=True)

        fetcher.process_trade_date.assert_has_calls(
            [
                unittest.mock.call("20260317", stock_codes=["000001.SZ", "000002.SZ"]),
                unittest.mock.call("20260318", stock_codes=["000001.SZ", "000002.SZ"]),
            ]
        )
        fetcher.process_stock.assert_not_called()

    def test_process_stock_rescales_existing_qfq_history_when_latest_adj_factor_changes(self):
        fetcher = DataFetcher.__new__(DataFetcher)
        fetcher.db = Mock()
        fetcher.db.get_latest_adj_factor.return_value = 1.0
        fetcher.fetch_daily_data = Mock(
            return_value=pd.DataFrame(
                [
                    {
                        "ts_code": "688256.SH",
                        "trade_date": "20260508",
                        "open": 12.0,
                        "high": 12.5,
                        "low": 11.8,
                        "close": 12.2,
                        "pre_close": 11.9,
                        "change": 0.3,
                        "pct_chg": 2.5,
                        "vol": 1000,
                        "amount": 2000,
                        "adj_factor": 1.5,
                    }
                ]
            )
        )
        fetcher.db.get_daily_ohlcv.return_value = pd.DataFrame(
            [
                {
                    "ts_code": "688256.SH",
                    "trade_date": "20260507",
                    "open": 8.0,
                    "high": 8.5,
                    "low": 7.8,
                    "close": 8.2,
                    "pre_close": 7.9,
                    "change": 0.3,
                    "pct_chg": 3.8,
                    "vol": 900,
                    "amount": 1800,
                    "adj_factor": 1.0,
                },
                {
                    "ts_code": "688256.SH",
                    "trade_date": "20260508",
                    "open": 12.0,
                    "high": 12.5,
                    "low": 11.8,
                    "close": 12.2,
                    "pre_close": 11.9,
                    "change": 0.3,
                    "pct_chg": 2.5,
                    "vol": 1000,
                    "amount": 2000,
                    "adj_factor": 1.5,
                },
            ]
        )
        expected_indicators = pd.DataFrame(
            [
                {"ts_code": "688256.SH", "trade_date": "20260507", "ma5": 8.2},
                {"ts_code": "688256.SH", "trade_date": "20260508", "ma5": 12.2},
            ]
        )
        fetcher.calculate_indicators = Mock(return_value=expected_indicators)

        ok = fetcher.process_stock("688256.SH", "20260508", "20260508", replace=False)

        self.assertTrue(ok)
        fetcher.db.rescale_qfq_history.assert_called_once_with(
            "688256.SH",
            scale_ratio=1.0 / 1.5,
            before_trade_date="20260508",
        )
        fetcher.db.insert_daily_ohlcv.assert_called_once()
        fetcher.db.insert_daily_indicators.assert_called_once_with(
            expected_indicators,
            replace=True,
        )

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

    def test_rescale_qfq_history_scales_only_price_fields(self):
        db = StockDatabase(":memory:")
        try:
            rows = pd.DataFrame(
                [
                    {
                        "ts_code": "688256.SH",
                        "trade_date": "20260507",
                        "open": 100.0,
                        "high": 110.0,
                        "low": 90.0,
                        "close": 105.0,
                        "pre_close": 95.0,
                        "change": 10.0,
                        "pct_chg": 10.5,
                        "vol": 1000,
                        "amount": 2000,
                        "adj_factor": 1.0,
                    },
                    {
                        "ts_code": "688256.SH",
                        "trade_date": "20260508",
                        "open": 120.0,
                        "high": 125.0,
                        "low": 118.0,
                        "close": 122.0,
                        "pre_close": 119.0,
                        "change": 2.0,
                        "pct_chg": 1.7,
                        "vol": 1200,
                        "amount": 2400,
                        "adj_factor": 1.5,
                    },
                ]
            )
            db.insert_daily_ohlcv(rows, replace=False)

            db.rescale_qfq_history("688256.SH", scale_ratio=0.5, before_trade_date="20260508")

            result = db.get_daily_ohlcv("688256.SH")
            first_row = result[result["trade_date"] == "20260507"].iloc[0]
            second_row = result[result["trade_date"] == "20260508"].iloc[0]

            self.assertEqual(first_row["open"], 50.0)
            self.assertEqual(first_row["close"], 52.5)
            self.assertEqual(first_row["change"], 10.0)
            self.assertEqual(second_row["open"], 120.0)
        finally:
            db.close()

    def test_main_update_all_from_db_uses_batch_trade_date_path(self):
        fetcher = Mock()

        with patch.object(
            sys,
            "argv",
            ["fetch_data_to_db.py", "--update", "--all-from-db"],
        ), patch(
            "database.fetch_data_to_db.DataFetcher",
            return_value=fetcher,
        ):
            fetch_data_to_db_module.main()

        fetcher.update_database.assert_called_once_with(
            stock_codes=None,
            incremental=True,
        )
        fetcher.close.assert_called_once_with()

    def test_main_rejects_all_from_db_with_explicit_stock_selection(self):
        with patch.object(
            sys,
            "argv",
            ["fetch_data_to_db.py", "--update", "--all-from-db", "--pool", "pool/stock_pool_all.txt"],
        ), patch(
            "database.fetch_data_to_db.DataFetcher",
        ) as fetcher_cls, patch(
            "database.fetch_data_to_db.logger.error",
        ) as logger_error:
            fetch_data_to_db_module.main()

        fetcher_cls.assert_not_called()
        logger_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
