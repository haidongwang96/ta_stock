#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量更新最新财务指标到本地数据库。

数据写入 financial_metrics 表，不混入日行情或技术指标表。
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from typing import Callable, List, Optional

import pandas as pd
import tushare as ts

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.db_manager import StockDatabase


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

RATE_LIMIT_KEYWORDS = [
    '频率超限',
    'rate limit',
    'too many requests',
]


INCOME_FIELDS = [
    'ts_code',
    'ann_date',
    'end_date',
    'total_revenue',
    'revenue',
    'total_profit',
    'n_income',
    'sell_exp',
    'admin_exp',
    'rd_exp',
]

INDICATOR_FIELDS = [
    'ts_code',
    'ann_date',
    'end_date',
    'grossprofit_margin',
    'netprofit_margin',
    'profit_dedt',
    'roe',
    'roic',
    'debt_to_assets',
]

CASHFLOW_FIELDS = [
    'ts_code',
    'ann_date',
    'end_date',
    'n_cashflow_act',
]


def read_stock_pool(pool_file: str) -> List[str]:
    """读取股票池文件，支持空行和 # 注释。"""
    if not os.path.exists(pool_file):
        logger.error(f"股票池文件不存在: {pool_file}")
        return []

    stock_codes = []
    with open(pool_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            code = line.split('#')[0].strip()
            if code:
                stock_codes.append(code)

    logger.info(f"从 {pool_file} 读取到 {len(stock_codes)} 只股票")
    return stock_codes


def get_recent_periods(num_periods: int) -> List[str]:
    """按财报披露节奏生成最近 N 个报告期。"""
    current_date = datetime.now()
    year = current_date.year
    month = current_date.month

    if month >= 11:
        period_suffixes = ['0930', '0630', '0331', '1231']
        years = [year, year, year, year - 1]
    elif month >= 8:
        period_suffixes = ['0630', '0331', '1231', '0930']
        years = [year, year, year - 1, year - 1]
    elif month >= 5:
        period_suffixes = ['0331', '1231', '0930', '0630']
        years = [year, year - 1, year - 1, year - 1]
    else:
        period_suffixes = ['1231', '0930', '0630', '0331']
        years = [year - 1, year - 1, year - 1, year - 1]

    periods = [f"{years[i]}{period_suffixes[i]}" for i in range(min(num_periods, 4))]
    quarter_order = ['0331', '0630', '0930', '1231']

    while len(periods) < num_periods:
        last_period = periods[-1]
        last_year = int(last_period[:4])
        suffix = last_period[4:]
        suffix_idx = quarter_order.index(suffix) - 1
        if suffix_idx < 0:
            suffix_idx = 3
            last_year -= 1
        periods.append(f"{last_year}{quarter_order[suffix_idx]}")

    return periods


def period_type_from_end_date(end_date: Optional[str]) -> Optional[str]:
    """将报告期截止日映射为 Q1/H1/Q3/FY。"""
    if not end_date or len(str(end_date)) < 8:
        return None

    suffix = str(end_date)[4:8]
    return {
        '0331': 'Q1',
        '0630': 'H1',
        '0930': 'Q3',
        '1231': 'FY',
    }.get(suffix)


class FinancialMetricsUpdater:
    """从 Tushare 拉取财务指标并写入本地数据库。"""

    def __init__(
        self,
        db_path: str = None,
        max_calls_per_minute: int = 180,
        init_tushare: bool = True,
    ):
        self.pro = self._init_tushare() if init_tushare else None
        self.db = StockDatabase(db_path)
        self.max_calls_per_minute = max_calls_per_minute
        self.call_timestamps = {}

    def _init_tushare(self):
        token_file = os.path.join(project_root, 'token.txt')
        if not os.path.exists(token_file):
            raise FileNotFoundError(f"未找到token文件: {token_file}")

        with open(token_file, 'r', encoding='utf-8') as f:
            token = f.read().strip()

        if not token:
            raise ValueError("token.txt文件为空")

        ts.set_token(token)
        return ts.pro_api()

    def fetch_stock_metrics(
        self,
        ts_code: str,
        periods: List[str],
        include_cashflow: bool = False,
    ) -> pd.DataFrame:
        """获取单只股票最近报告期财务指标。"""
        income_rows = []
        indicator_rows = []
        cashflow_rows = []

        for period in periods:
            try:
                income_df = self.pro.income(
                    ts_code=ts_code,
                    period=period,
                    fields=','.join(INCOME_FIELDS),
                )
                if income_df is not None and not income_df.empty:
                    income_rows.append(income_df)
            except Exception as e:
                logger.warning(f"{ts_code} {period} 利润表获取失败: {e}")

            try:
                indicator_df = self.pro.fina_indicator(
                    ts_code=ts_code,
                    period=period,
                    fields=','.join(INDICATOR_FIELDS),
                )
                if indicator_df is not None and not indicator_df.empty:
                    indicator_rows.append(indicator_df)
            except Exception as e:
                logger.warning(f"{ts_code} {period} 财务指标获取失败: {e}")

            if include_cashflow:
                try:
                    cashflow_df = self.pro.cashflow(
                        ts_code=ts_code,
                        period=period,
                        fields=','.join(CASHFLOW_FIELDS),
                    )
                    if cashflow_df is not None and not cashflow_df.empty:
                        cashflow_rows.append(cashflow_df)
                except Exception as e:
                    logger.warning(f"{ts_code} {period} 现金流量表获取失败: {e}")

        income = pd.concat(income_rows, ignore_index=True) if income_rows else pd.DataFrame()
        indicator = pd.concat(indicator_rows, ignore_index=True) if indicator_rows else pd.DataFrame()
        cashflow = pd.concat(cashflow_rows, ignore_index=True) if cashflow_rows else pd.DataFrame()

        if income.empty and indicator.empty and cashflow.empty:
            return pd.DataFrame()

        income = self._dedupe_by_latest_ann_date(income)
        indicator = self._dedupe_by_latest_ann_date(indicator)
        cashflow = self._dedupe_by_latest_ann_date(cashflow)

        return self._normalize_metrics(self._merge_metric_frames(income, indicator, cashflow))

    def fetch_income_metric(self, ts_code: str, period: str) -> Optional[dict]:
        """单只股票拉取利润表。income 接口不可靠支持逗号批量 ts_code。"""
        for attempt in range(4):
            self._throttle_api('利润表')
            try:
                income = self.pro.income(
                    ts_code=ts_code,
                    period=period,
                    fields=','.join(INCOME_FIELDS),
                )
                break
            except Exception as e:
                if self._is_rate_limit_error(e):
                    logger.warning(
                        f"{ts_code} {period} income触发频率限制，等待65秒后重试 "
                        f"({attempt + 1}/4): {e}"
                    )
                    time.sleep(65)
                    continue
                raise
        else:
            return None

        if income is None or income.empty:
            return None

        income = self._dedupe_by_latest_ann_date(income)
        row = income.iloc[0]
        profit = row.get('n_income')
        if pd.isna(profit):
            profit = row.get('total_profit')

        revenue = row.get('total_revenue')
        if pd.isna(revenue):
            revenue = row.get('revenue')

        return {
            'report_date': self._nullable_value(row.get('ann_date')),
            'profit': self._nullable_value(profit),
            'revenue': self._nullable_value(revenue),
        }

    def fetch_period_income_vip(self, period: str) -> pd.DataFrame:
        """使用 income_vip 按报告期批量拉取全部股票利润表。"""
        try:
            self._throttle_api('利润表VIP')
            income = self.pro.income_vip(
                period=period,
                report_type='1',
                fields=','.join(INCOME_FIELDS),
            )
            return income if income is not None else pd.DataFrame()
        except Exception as e:
            logger.warning(f"{period} income_vip批量获取失败，将依赖单股补齐: {e}")
            return pd.DataFrame()

    def fetch_period_cashflow_vip(
        self,
        period: str,
        stock_codes: List[str],
        batch_size: int,
    ) -> pd.DataFrame:
        """使用 cashflow_vip 按股票池分批拉取现金流量表。"""
        return self._fetch_period_api_in_batches(
            api_func=self.pro.cashflow_vip,
            api_name='现金流量表VIP',
            period=period,
            stock_codes=stock_codes,
            fields=CASHFLOW_FIELDS,
            batch_size=batch_size,
        )

    def fetch_period_metrics(
        self,
        period: str,
        stock_codes: List[str],
        batch_size: int = 80,
        include_cashflow: bool = False,
    ) -> pd.DataFrame:
        """按报告期分批获取股票池财务指标。"""
        income = self.fetch_period_income_vip(period)
        cashflow = (
            self.fetch_period_cashflow_vip(period, stock_codes, batch_size)
            if include_cashflow else pd.DataFrame()
        )
        indicator = self._fetch_period_api_in_batches(
            api_func=self.pro.fina_indicator,
            api_name='财务指标',
            period=period,
            stock_codes=stock_codes,
            fields=INDICATOR_FIELDS,
            batch_size=batch_size,
        )

        if (
            (income is None or income.empty)
            and (indicator is None or indicator.empty)
            and (cashflow is None or cashflow.empty)
        ):
            return pd.DataFrame()

        income = self._dedupe_by_latest_ann_date(income) if income is not None else pd.DataFrame()
        indicator = (
            self._dedupe_by_latest_ann_date(indicator)
            if indicator is not None else pd.DataFrame()
        )
        cashflow = self._dedupe_by_latest_ann_date(cashflow) if cashflow is not None else pd.DataFrame()

        return self._normalize_metrics(self._merge_metric_frames(income, indicator, cashflow))

    def _merge_metric_frames(
        self,
        income: pd.DataFrame,
        indicator: pd.DataFrame,
        cashflow: pd.DataFrame,
    ) -> pd.DataFrame:
        frames = []
        if income is not None and not income.empty:
            frames.append(income.rename(columns={'ann_date': 'ann_date_income'}))
        if indicator is not None and not indicator.empty:
            frames.append(indicator.rename(columns={'ann_date': 'ann_date_indicator'}))
        if cashflow is not None and not cashflow.empty:
            frames.append(cashflow.rename(columns={'ann_date': 'ann_date_cashflow'}))

        if not frames:
            return pd.DataFrame()

        merged = frames[0]
        for frame in frames[1:]:
            merged = pd.merge(merged, frame, on=['ts_code', 'end_date'], how='outer')
        return merged

    def _fetch_period_api_in_batches(
        self,
        api_func: Callable,
        api_name: str,
        period: str,
        stock_codes: List[str],
        fields: List[str],
        batch_size: int,
    ) -> pd.DataFrame:
        """使用逗号分隔 ts_code 分批拉取；限频等待，普通批量错误拆小。"""
        frames = []
        batch_size = max(1, batch_size)

        for start in range(0, len(stock_codes), batch_size):
            batch = stock_codes[start:start + batch_size]
            batch_df = self._fetch_period_api_batch(
                api_func=api_func,
                api_name=api_name,
                period=period,
                stock_codes=batch,
                fields=fields,
                max_retries=3,
            )
            if batch_df is not None and not batch_df.empty:
                frames.append(batch_df)

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _fetch_period_api_batch(
        self,
        api_func: Callable,
        api_name: str,
        period: str,
        stock_codes: List[str],
        fields: List[str],
        max_retries: int,
    ) -> pd.DataFrame:
        """拉取一个批次；限频错误等待重试，其他批量错误递归二分。"""
        if not stock_codes:
            return pd.DataFrame()

        ts_code_arg = ','.join(stock_codes)
        for attempt in range(max_retries + 1):
            self._throttle_api(api_name)
            try:
                df = api_func(
                    ts_code=ts_code_arg,
                    period=period,
                    fields=','.join(fields),
                )
                return df if df is not None else pd.DataFrame()
            except Exception as e:
                if self._is_rate_limit_error(e):
                    wait_seconds = 65
                    logger.warning(
                        f"{period} {api_name}触发频率限制，等待 {wait_seconds} 秒后重试 "
                        f"({attempt + 1}/{max_retries + 1}): {e}"
                    )
                    time.sleep(wait_seconds)
                    continue

                if len(stock_codes) == 1:
                    logger.warning(f"{stock_codes[0]} {period} {api_name}获取失败: {e}")
                    return pd.DataFrame()

                midpoint = len(stock_codes) // 2
                logger.warning(
                    f"{period} {api_name}批量获取失败，拆分 {len(stock_codes)} 只股票重试: {e}"
                )
                left = self._fetch_period_api_batch(
                    api_func=api_func,
                    api_name=api_name,
                    period=period,
                    stock_codes=stock_codes[:midpoint],
                    fields=fields,
                    max_retries=max_retries,
                )
                right = self._fetch_period_api_batch(
                    api_func=api_func,
                    api_name=api_name,
                    period=period,
                    stock_codes=stock_codes[midpoint:],
                    fields=fields,
                    max_retries=max_retries,
                )
                frames = [df for df in [left, right] if df is not None and not df.empty]
                return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        logger.warning(f"{period} {api_name}超过重试次数，跳过 {len(stock_codes)} 只股票")
        return pd.DataFrame()

    def _throttle_api(self, api_name: str):
        """按接口名称做分钟级限速，避免触发 Tushare 频控。"""
        now = time.monotonic()
        window_start = now - 60
        timestamps = [
            timestamp
            for timestamp in self.call_timestamps.get(api_name, [])
            if timestamp > window_start
        ]

        if len(timestamps) >= self.max_calls_per_minute:
            wait_seconds = 60 - (now - timestamps[0]) + 1
            logger.info(f"{api_name}接近频率上限，等待 {wait_seconds:.1f} 秒")
            time.sleep(wait_seconds)
            now = time.monotonic()
            window_start = now - 60
            timestamps = [timestamp for timestamp in timestamps if timestamp > window_start]

        timestamps.append(time.monotonic())
        self.call_timestamps[api_name] = timestamps

    def _is_rate_limit_error(self, error: Exception) -> bool:
        message = str(error).lower()
        return any(keyword.lower() in message for keyword in RATE_LIMIT_KEYWORDS)

    def _dedupe_by_latest_ann_date(self, df: pd.DataFrame) -> pd.DataFrame:
        """同一报告期可能有修订公告，保留公告日期最新的一条。"""
        if df.empty:
            return df

        sort_columns = [col for col in ['end_date', 'ann_date'] if col in df.columns]
        if sort_columns:
            df = df.sort_values(sort_columns, ascending=True)

        return df.drop_duplicates(subset=['ts_code', 'end_date'], keep='last')

    def _normalize_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        has_cashflow = 'n_cashflow_act' in df.columns
        for _, row in df.iterrows():
            end_date = row.get('end_date')
            if pd.isna(end_date):
                continue

            ann_date = self._latest_date_value(
                row.get('ann_date_income'),
                row.get('ann_date_indicator'),
                row.get('ann_date_cashflow'),
                row.get('ann_date'),
            )
            report_date = ann_date if not pd.isna(ann_date) else end_date
            profit = row.get('n_income')
            if pd.isna(profit):
                profit = row.get('total_profit')

            revenue = row.get('total_revenue')
            if pd.isna(revenue):
                revenue = row.get('revenue')

            operating_cash_flow = row.get('n_cashflow_act') if has_cashflow else None
            ocf_to_profit = None
            if not pd.isna(operating_cash_flow) and not pd.isna(profit) and profit != 0:
                ocf_to_profit = operating_cash_flow / profit

            sales_expense = row.get('sell_exp')
            admin_expense = row.get('admin_exp')
            rd_expense = row.get('rd_exp')

            result_row = {
                'ts_code': row.get('ts_code'),
                'report_date': str(report_date),
                'end_date': str(end_date),
                'period_type': period_type_from_end_date(str(end_date)),
                'profit': None if pd.isna(profit) else profit,
                'revenue': None if pd.isna(revenue) else revenue,
                'gross_margin': self._nullable_value(row.get('grossprofit_margin')),
                'net_margin': self._nullable_value(row.get('netprofit_margin')),
                'deducted_profit': self._nullable_value(row.get('profit_dedt')),
                'roe': self._nullable_value(row.get('roe')),
                'roic': self._nullable_value(row.get('roic')),
                'debt_to_assets': self._nullable_value(row.get('debt_to_assets')),
                'sales_expense': self._nullable_value(sales_expense),
                'admin_expense': self._nullable_value(admin_expense),
                'rd_expense': self._nullable_value(rd_expense),
                'sales_expense_rate': self._expense_rate(sales_expense, revenue),
                'admin_expense_rate': self._expense_rate(admin_expense, revenue),
                'rd_expense_rate': self._expense_rate(rd_expense, revenue),
            }
            if has_cashflow:
                result_row['operating_cash_flow'] = self._nullable_value(operating_cash_flow)
                result_row['ocf_to_profit'] = self._nullable_value(ocf_to_profit)
            rows.append(result_row)

        if not rows:
            return pd.DataFrame()

        result = pd.DataFrame(rows)
        return result.sort_values(['report_date', 'end_date'], ascending=False)

    def _nullable_value(self, value):
        return None if pd.isna(value) else value

    def _expense_rate(self, expense, revenue):
        if pd.isna(expense) or pd.isna(revenue) or revenue == 0:
            return None
        return expense / revenue * 100

    def _latest_date_value(self, *values):
        valid_values = [str(value) for value in values if not pd.isna(value)]
        return max(valid_values) if valid_values else None

    def get_missing_income_targets(
        self,
        stock_codes: List[str],
        latest_only: bool = True,
    ) -> pd.DataFrame:
        """查询已入库但缺少利润或营收的记录。"""
        placeholders = ','.join(['?'] * len(stock_codes))
        query = f"""
            SELECT id, ts_code, report_date, end_date, period_type, profit, revenue
            FROM financial_metrics
            WHERE ts_code IN ({placeholders})
              AND (profit IS NULL OR revenue IS NULL)
            ORDER BY ts_code ASC, report_date DESC, end_date DESC
        """
        targets = pd.read_sql_query(query, self.db.conn, params=stock_codes)
        if targets.empty or not latest_only:
            return targets

        return targets.groupby('ts_code', as_index=False).head(1)

    def repair_missing_income(
        self,
        stock_codes: List[str],
        latest_only: bool = True,
    ):
        """对缺失 profit/revenue 的记录逐股补拉 income。"""
        targets = self.get_missing_income_targets(stock_codes, latest_only=latest_only)
        if targets.empty:
            logger.info("没有需要补齐利润/营收的财务记录")
            return

        logger.info(f"开始补齐利润/营收，共 {len(targets)} 条记录")
        success_count = 0
        empty_count = 0
        fail_count = 0

        for index, row in enumerate(targets.itertuples(index=False), start=1):
            try:
                income = self.fetch_income_metric(row.ts_code, row.end_date)
                if not income:
                    empty_count += 1
                    continue

                report_date = self._latest_date_value(row.report_date, income['report_date'])
                self._merge_income_into_metric(
                    metric_id=row.id,
                    ts_code=row.ts_code,
                    end_date=row.end_date,
                    period_type=row.period_type,
                    report_date=report_date,
                    profit=income['profit'],
                    revenue=income['revenue'],
                )
                success_count += 1
                if success_count % 200 == 0:
                    self.db.conn.commit()
                    logger.info(f"已补齐 {success_count}/{len(targets)} 条利润/营收")
            except Exception as e:
                fail_count += 1
                logger.warning(f"{row.ts_code} {row.end_date} income补齐失败: {e}")

        self.db.conn.commit()
        logger.info(
            f"利润/营收补齐完成：成功 {success_count}，无数据 {empty_count}，失败 {fail_count}"
        )

    def _merge_income_into_metric(
        self,
        metric_id: int,
        ts_code: str,
        end_date: str,
        period_type: str,
        report_date: str,
        profit,
        revenue,
    ):
        """补齐 income；如果目标唯一键已存在，则合并后删除当前空记录。"""
        updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        existing = self.db.conn.execute(
            """
            SELECT id
            FROM financial_metrics
            WHERE ts_code = ?
              AND report_date = ?
              AND COALESCE(end_date, '') = COALESCE(?, '')
              AND COALESCE(period_type, '') = COALESCE(?, '')
              AND id != ?
            LIMIT 1
            """,
            (ts_code, report_date, end_date, period_type, metric_id),
        ).fetchone()

        if existing:
            self.db.conn.execute(
                """
                UPDATE financial_metrics
                SET profit = COALESCE(profit, ?),
                    revenue = COALESCE(revenue, ?),
                    gross_margin = COALESCE(gross_margin, (
                        SELECT gross_margin FROM financial_metrics WHERE id = ?
                    )),
                    net_margin = COALESCE(net_margin, (
                        SELECT net_margin FROM financial_metrics WHERE id = ?
                    )),
                    updated_at = ?
                WHERE id = ?
                """,
                (profit, revenue, metric_id, metric_id, updated_at, existing[0]),
            )
            self.db.conn.execute("DELETE FROM financial_metrics WHERE id = ?", (metric_id,))
            return

        self.db.conn.execute(
            """
            UPDATE financial_metrics
            SET report_date = ?,
                profit = COALESCE(?, profit),
                revenue = COALESCE(?, revenue),
                updated_at = ?
            WHERE id = ?
            """,
            (report_date, profit, revenue, updated_at, metric_id),
        )


    def update_pool(
        self,
        stock_codes: List[str],
        periods: List[str],
        latest_only: bool = True,
        sleep_seconds: float = 0.2,
        include_cashflow: bool = False,
    ):
        total = len(stock_codes)
        success_count = 0
        empty_count = 0
        fail_count = 0

        logger.info(
            f"开始更新财务指标，共 {total} 只股票，扫描报告期: {', '.join(periods)}"
        )

        for index, ts_code in enumerate(stock_codes, start=1):
            try:
                metrics = self.fetch_stock_metrics(
                    ts_code,
                    periods,
                    include_cashflow=include_cashflow,
                )
                if metrics.empty:
                    empty_count += 1
                    logger.warning(f"[{index}/{total}] {ts_code} 未获取到财务指标")
                    continue

                if latest_only:
                    metrics = metrics.head(1)

                self.db.insert_financial_metrics(metrics, replace=True)
                success_count += 1
                latest = metrics.iloc[0]
                logger.info(
                    f"[{index}/{total}] {ts_code} 已更新 {len(metrics)} 条，"
                    f"最新报告期 {latest['end_date']} / 公告日 {latest['report_date']}"
                )
            except Exception as e:
                fail_count += 1
                logger.error(f"[{index}/{total}] {ts_code} 更新失败: {e}", exc_info=True)

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        logger.info(
            f"财务指标更新完成：成功 {success_count}，无数据 {empty_count}，失败 {fail_count}，总计 {total}"
        )
        self.db.update_financial_growth_metrics(stock_codes)

    def update_pool_by_period(
        self,
        stock_codes: List[str],
        periods: List[str],
        latest_only: bool = True,
        sleep_seconds: float = 0.2,
        batch_size: int = 80,
        repair_income: bool = True,
        include_cashflow: bool = False,
    ):
        """按报告期分批拉取股票池财务数据。"""
        stock_set = set(stock_codes)
        metric_frames = []

        logger.info(
            f"开始按报告期分批更新财务指标，股票池 {len(stock_set)} 只，"
            f"每批 {batch_size} 只，"
            f"扫描报告期: {', '.join(periods)}"
        )

        for index, period in enumerate(periods, start=1):
            metrics = self.fetch_period_metrics(
                period=period,
                stock_codes=stock_codes,
                batch_size=batch_size,
                include_cashflow=include_cashflow,
            )
            if metrics.empty:
                logger.warning(f"[{index}/{len(periods)}] {period} 未获取到财务指标")
            else:
                metrics = metrics[metrics['ts_code'].isin(stock_set)].copy()
                if not metrics.empty:
                    metric_frames.append(metrics)
                logger.info(
                    f"[{index}/{len(periods)}] {period} 获取并匹配 {len(metrics)} 条股票池记录"
                )

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if not metric_frames:
            logger.warning("未匹配到任何股票池财务指标")
            return

        all_metrics = pd.concat(metric_frames, ignore_index=True)
        all_metrics = all_metrics.sort_values(['ts_code', 'report_date', 'end_date'])
        all_metrics = all_metrics.drop_duplicates(
            subset=['ts_code', 'report_date', 'end_date', 'period_type'],
            keep='last',
        )

        if latest_only:
            all_metrics = (
                all_metrics
                .sort_values(['ts_code', 'report_date', 'end_date'], ascending=[True, False, False])
                .groupby('ts_code', as_index=False)
                .head(1)
            )

        self.db.insert_financial_metrics(all_metrics, replace=True)

        updated_codes = set(all_metrics['ts_code'])
        missing_codes = stock_set - updated_codes
        logger.info(
            f"财务指标批量更新完成：写入 {len(all_metrics)} 条，"
            f"覆盖股票 {len(updated_codes)} 只，无数据 {len(missing_codes)} 只"
        )

        if repair_income:
            self.repair_missing_income(stock_codes, latest_only=latest_only)

        self.db.update_financial_growth_metrics(stock_codes)

    def close(self):
        self.db.close()


def main():
    parser = argparse.ArgumentParser(description='批量更新最新财务指标到 financial_metrics 表')
    parser.add_argument('--pool', required=True, help='股票池文件路径')
    parser.add_argument('--db', help='数据库文件路径，默认项目根目录 stock_data.db')
    parser.add_argument('--periods', type=int, default=8, help='向前扫描的报告期数量，默认8')
    parser.add_argument(
        '--all-periods',
        action='store_true',
        help='保存扫描到的全部报告期；默认每只股票只保存最新一条',
    )
    parser.add_argument(
        '--repair-only',
        action='store_true',
        help='不重新拉取指标，只补齐库中缺失的profit/revenue',
    )
    parser.add_argument(
        '--calc-growth-only',
        action='store_true',
        help='不重新拉取数据，只基于库中financial_metrics重算单季值、同比和环比',
    )
    parser.add_argument(
        '--skip-income-repair',
        action='store_true',
        help='跳过income单股补齐，速度更快但profit/revenue可能为空',
    )
    parser.add_argument(
        '--include-cashflow',
        action='store_true',
        help='拉取经营现金流；部分Tushare账号cashflow_vip只有1次/分钟，默认跳过',
    )
    parser.add_argument(
        '--fetch-mode',
        choices=['period', 'stock'],
        default='period',
        help='拉取模式：period=按报告期分批拉股票池，stock=逐只股票拉取；默认period',
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=80,
        help='period模式下每批股票数，默认80；过大可能被Tushare单次返回上限截断',
    )
    parser.add_argument(
        '--max-calls-per-minute',
        type=int,
        default=180,
        help='单个Tushare接口每分钟最大调用数，默认180，低于常见200次/分钟限制',
    )
    parser.add_argument('--sleep', type=float, default=0.2, help='每只股票之间的等待秒数，默认0.2')

    args = parser.parse_args()

    stock_codes = read_stock_pool(args.pool)
    if not stock_codes:
        logger.error("股票池为空，退出")
        sys.exit(1)

    periods = get_recent_periods(args.periods)
    updater = FinancialMetricsUpdater(
        db_path=args.db,
        max_calls_per_minute=args.max_calls_per_minute,
        init_tushare=not args.calc_growth_only,
    )
    try:
        if args.calc_growth_only:
            updater.db.update_financial_growth_metrics(stock_codes)
        elif args.repair_only:
            updater.repair_missing_income(
                stock_codes=stock_codes,
                latest_only=not args.all_periods,
            )
            updater.db.update_financial_growth_metrics(stock_codes)
        elif args.fetch_mode == 'period':
            updater.update_pool_by_period(
                stock_codes=stock_codes,
                periods=periods,
                latest_only=not args.all_periods,
                sleep_seconds=args.sleep,
                batch_size=args.batch_size,
                repair_income=not args.skip_income_repair,
                include_cashflow=args.include_cashflow,
            )
        else:
            updater.update_pool(
                stock_codes=stock_codes,
                periods=periods,
                latest_only=not args.all_periods,
                sleep_seconds=args.sleep,
                include_cashflow=args.include_cashflow,
            )
    finally:
        updater.close()


if __name__ == '__main__':
    main()
