"""
年度价格统计辅助函数。
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd


def get_year_start_date(end_date: str | None = None) -> str:
    """根据分析截止日返回当年首日 YYYYMMDD。"""
    if end_date:
        return f"{str(end_date)[:4]}0101"
    return f"{datetime.now().year}0101"


def _get_column(df: pd.DataFrame, *candidates: str) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column
    return None


def _normalize_trade_date(value) -> str:
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y%m%d")
    if hasattr(value, "strftime"):
        return value.strftime("%Y%m%d")

    value_str = str(value)
    if len(value_str) >= 10 and "-" in value_str:
        return value_str[:10].replace("-", "")
    return value_str


def _round_value(value: float | None, precision: int = 2) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), precision)


def calculate_year_stats(df: pd.DataFrame) -> dict | None:
    """根据年内行情数据生成统计快照。"""
    if df is None or df.empty:
        return None

    high_col = _get_column(df, "high", "High")
    close_col = _get_column(df, "close", "Close")
    date_col = _get_column(df, "trade_date")

    if not all([high_col, close_col, date_col]):
        return None

    year_df = df.sort_values(date_col, ascending=True).reset_index(drop=True)
    latest_row = year_df.iloc[-1]

    current_price = latest_row[close_col]
    year_high = year_df[high_col].max()
    year_high_close = year_df[close_col].max()

    high_date = None
    drop_from_high_pct = None
    if pd.notna(year_high) and year_high > 0:
        high_row = year_df.loc[year_df[high_col].idxmax()]
        high_date = _normalize_trade_date(high_row[date_col])
        drop_from_high_pct = (year_high - current_price) / year_high * 100

    return {
        "current_price": _round_value(current_price),
        "year_high": _round_value(year_high),
        "year_high_date": high_date,
        "year_high_close": _round_value(year_high_close),
        "drop_from_year_high_pct": _round_value(drop_from_high_pct),
        "latest_date": _normalize_trade_date(latest_row[date_col]),
    }
