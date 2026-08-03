"""Authenticated, in-memory realtime quote service backed by mootdx.

This service deliberately stores no intraday data.  It keeps only a short-lived
process-local cache so overlapping stock pools do not hit the quote server more
than once per refresh cycle.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hmac
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

MAX_SYMBOLS = 300
QUOTE_BATCH_SIZE = 80
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def normalize_symbol(value: str) -> str:
    """Convert a Tushare-style code to the six-digit symbol mootdx expects."""
    code, separator, market = value.strip().upper().partition(".")
    if not separator or market not in {"SH", "SZ"} or len(code) != 6 or not code.isdigit():
        raise ValueError(f"unsupported stock code: {value}")
    return code


def ts_code_for(symbol: str, market: object) -> str:
    """Map the mootdx numeric market back to a Tushare-style code."""
    try:
        suffix = "SH" if int(market) == 1 else "SZ"
    except (TypeError, ValueError):
        suffix = "SH" if symbol.startswith(("5", "6", "9")) else "SZ"
    return f"{symbol}.{suffix}"


def finite_float(value: object) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def secret_matches(expected: str, supplied: Optional[str]) -> bool:
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


@dataclass(frozen=True)
class Quote:
    ts_code: str
    price: Optional[float]
    pre_close: Optional[float]
    pct_chg: Optional[float]
    quote_time: Optional[str]
    fetched_at: str
    available: bool


@dataclass
class CacheEntry:
    quote: Quote
    cached_at: float


class QuoteProvider:
    """Lazy mootdx connection with reconnect-on-failure behavior."""

    def __init__(self) -> None:
        self._client = None
        self._lock = threading.Lock()

    def fetch(self, symbols: list[str]) -> pd.DataFrame:
        with self._lock:
            try:
                if self._client is not None:
                    result = self._client.quotes(symbols)
                    if isinstance(result, pd.DataFrame) and not result.empty:
                        return result
                self.close()
                return self._discover_and_fetch(symbols)
            except Exception:
                self.close()
                raise

    def _discover_and_fetch(self, symbols: list[str]) -> pd.DataFrame:
        """Find a working TDX node without relying on mootdx's stale BESTIP."""
        from mootdx.quotes import Quotes
        from mootdx.server import connect2, hosts

        candidates = []
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [
                executor.submit(connect2, dict(server), "HQ")
                for server in hosts["HQ"]
            ]
            for future in as_completed(futures):
                result = future.result()
                if result.get("time") is not None:
                    candidates.append(result)

        candidates.sort(key=lambda item: item["time"])
        for candidate in candidates[:8]:
            client = None
            try:
                client = Quotes.factory(
                    market="std",
                    server=(candidate["addr"], int(candidate["port"])),
                    timeout=3,
                )
                result = client.quotes(symbols)
                if isinstance(result, pd.DataFrame) and not result.empty:
                    self._client = client
                    logger.info("Connected to mootdx quote node %s:%s", candidate["addr"], candidate["port"])
                    return result
            except Exception:
                logger.debug("Rejected mootdx quote node %s", candidate["addr"], exc_info=True)
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

        raise ConnectionError("no working mootdx quote node")

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                logger.debug("Failed to close mootdx client", exc_info=True)
        self._client = None


class QuoteCache:
    def __init__(
        self,
        provider: QuoteProvider,
        ttl_seconds: float = 8.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.provider = provider
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()

    def get(self, ts_codes: list[str]) -> tuple[list[Quote], bool]:
        now = self.clock()
        with self._lock:
            missing = [
                code for code in ts_codes
                if code not in self._entries or now - self._entries[code].cached_at >= self.ttl_seconds
            ]

        delayed = False
        if missing:
            with self._refresh_lock:
                now = self.clock()
                with self._lock:
                    missing = [
                        code for code in ts_codes
                        if code not in self._entries
                        or now - self._entries[code].cached_at >= self.ttl_seconds
                    ]
                if missing:
                    try:
                        fetched = self._fetch(missing)
                        with self._lock:
                            for quote in fetched:
                                self._entries[quote.ts_code] = CacheEntry(quote=quote, cached_at=now)
                            for code in missing:
                                if code not in self._entries:
                                    self._entries[code] = CacheEntry(
                                        quote=self._unavailable(code), cached_at=now
                                    )
                            self._discard_old(now)
                    except Exception:
                        delayed = True
                        logger.warning("mootdx quote request failed", exc_info=True)

        with self._lock:
            quotes = [
                self._entries.get(code, CacheEntry(self._unavailable(code), now)).quote
                for code in ts_codes
            ]
        return quotes, delayed

    def _fetch(self, ts_codes: list[str]) -> list[Quote]:
        requested_by_symbol = {normalize_symbol(code): code for code in ts_codes}
        frames = []
        symbols = list(requested_by_symbol)
        for start in range(0, len(symbols), QUOTE_BATCH_SIZE):
            frame = self.provider.fetch(symbols[start:start + QUOTE_BATCH_SIZE])
            if not frame.empty:
                frames.append(frame)
        if not frames:
            return []

        fetched_at = datetime.now(SHANGHAI_TZ).isoformat(timespec="seconds")
        quotes = []
        for row in pd.concat(frames, ignore_index=True).to_dict("records"):
            symbol = str(row.get("code", "")).zfill(6)
            requested_code = requested_by_symbol.get(symbol)
            if requested_code is None:
                requested_code = ts_code_for(symbol, row.get("market"))
            price = finite_float(row.get("price"))
            pre_close = finite_float(row.get("last_close"))
            available = price is not None and pre_close is not None and price > 0 and pre_close > 0
            pct_chg = ((price - pre_close) / pre_close * 100) if available else None
            quotes.append(Quote(
                ts_code=requested_code,
                price=price if available else None,
                pre_close=pre_close if available else None,
                pct_chg=pct_chg,
                quote_time=str(row.get("servertime")) if row.get("servertime") else None,
                fetched_at=fetched_at,
                available=available,
            ))
        return quotes

    def _unavailable(self, ts_code: str) -> Quote:
        return Quote(
            ts_code=ts_code,
            price=None,
            pre_close=None,
            pct_chg=None,
            quote_time=None,
            fetched_at=datetime.now(SHANGHAI_TZ).isoformat(timespec="seconds"),
            available=False,
        )

    def _discard_old(self, now: float) -> None:
        max_age = max(300.0, self.ttl_seconds * 10)
        expired = [code for code, entry in self._entries.items() if now - entry.cached_at > max_age]
        for code in expired:
            self._entries.pop(code, None)


class QuoteRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=MAX_SYMBOLS)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, values: list[str]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            normalized = value.strip().upper()
            normalize_symbol(normalized)
            if normalized not in seen:
                result.append(normalized)
                seen.add(normalized)
        return result


def create_app(
    cache: Optional[QuoteCache] = None,
    secret: Optional[str] = None,
) -> FastAPI:
    quote_cache = cache or QuoteCache(QuoteProvider())
    expected_secret = secret if secret is not None else os.environ.get("MOOTDX_QUOTE_SECRET", "")
    app = FastAPI(title="ta_stock realtime quotes", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/quotes")
    async def quotes(
        request: QuoteRequest,
        x_quote_secret: Optional[str] = Header(default=None),
    ) -> dict[str, object]:
        if not secret_matches(expected_secret, x_quote_secret):
            raise HTTPException(status_code=401, detail="invalid quote service credentials")
        values, delayed = await run_in_threadpool(quote_cache.get, request.symbols)
        return {"quotes": [asdict(value) for value in values], "delayed": delayed}

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local mootdx realtime quote service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
