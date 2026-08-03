import unittest
from unittest.mock import Mock

import pandas as pd
from pydantic import ValidationError

from services.intraday_quote_service import QuoteCache, QuoteRequest, create_app, secret_matches


class IntradayQuoteServiceTest(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.provider = Mock()
        self.provider.fetch.return_value = pd.DataFrame([
            {
                "market": 1,
                "code": "600000",
                "price": 10.5,
                "last_close": 10.0,
                "servertime": "14:35:01",
            }
        ])
        self.cache = QuoteCache(self.provider, ttl_seconds=8, clock=lambda: self.now)

    def test_calculates_pct_change_and_reuses_short_cache(self):
        first, delayed = self.cache.get(["600000.SH"])
        second, _ = self.cache.get(["600000.SH"])

        self.assertFalse(delayed)
        self.assertAlmostEqual(first[0].pct_chg, 5.0)
        self.assertEqual(first, second)
        self.provider.fetch.assert_called_once_with(["600000"])

    def test_returns_stale_quote_when_refresh_fails(self):
        first, _ = self.cache.get(["600000.SH"])
        self.now += 9
        self.provider.fetch.side_effect = OSError("network down")

        second, delayed = self.cache.get(["600000.SH"])

        self.assertTrue(delayed)
        self.assertEqual(second, first)

    def test_api_requires_secret(self):
        self.assertFalse(secret_matches("test-secret", None))
        self.assertFalse(secret_matches("test-secret", "wrong"))
        self.assertTrue(secret_matches("test-secret", "test-secret"))
        route_paths = {route.path for route in create_app(cache=self.cache, secret="test-secret").routes}
        self.assertIn("/quotes", route_paths)
        self.assertIn("/health", route_paths)

    def test_api_rejects_unsupported_or_oversized_requests(self):
        with self.assertRaises(ValidationError):
            QuoteRequest(symbols=["430001.BJ"])
        with self.assertRaises(ValidationError):
            QuoteRequest(symbols=[f"{i:06d}.SZ" for i in range(301)])


if __name__ == "__main__":
    unittest.main()
