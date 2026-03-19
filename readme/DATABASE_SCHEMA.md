# 数据库结构说明

本项目使用本地 SQLite 数据库 `stock_data.db`。建表逻辑位于 `database/db_manager.py`，当前核心表有 4 张：

- `stock_basic`
- `daily_ohlcv`
- `daily_indicators`
- `rolling_scores`

整体设计偏分析型宽表结构：

- `stock_basic` 存股票基础信息
- `daily_ohlcv` 存原始日线行情
- `daily_indicators` 存技术指标
- `rolling_scores` 存滚动评分结果

其中，`daily_ohlcv`、`daily_indicators`、`rolling_scores` 都通过 `(ts_code, trade_date)` 关联。

## 表关系

```text
stock_basic
  ts_code (PK)
     |
     | 1:N
     v
daily_ohlcv
  id (PK)
  ts_code + trade_date (UNIQUE)
     |
     | 1:1 by (ts_code, trade_date)
     v
daily_indicators
  id (PK)
  ts_code + trade_date (UNIQUE)

daily_ohlcv
  ts_code + trade_date
     |
     | 1:1 by (ts_code, trade_date)
     v
rolling_scores
  id (PK)
  ts_code + trade_date (UNIQUE)
```

## 1. stock_basic

股票基础信息表，一只股票一行。

| 字段 | 含义 |
| --- | --- |
| `ts_code` | Tushare 股票代码，主键，例如 `000001.SZ` |
| `symbol` | 证券短代码，例如 `000001` |
| `name` | 股票名称 |
| `area` | 所属地区 |
| `industry` | 行业 |
| `market` | 市场或板块 |
| `list_date` | 上市日期 |
| `update_time` | 基础信息更新时间 |

## 2. daily_ohlcv

原始日线行情表，一只股票一个交易日一行，唯一键为 `ts_code + trade_date`。

| 字段 | 含义 |
| --- | --- |
| `id` | 自增主键 |
| `ts_code` | 股票代码 |
| `trade_date` | 交易日期，格式通常为 `YYYYMMDD` |
| `open` | 开盘价 |
| `high` | 最高价 |
| `low` | 最低价 |
| `close` | 收盘价 |
| `pre_close` | 前收盘价 |
| `change` | 涨跌额 |
| `pct_chg` | 涨跌幅 |
| `vol` | 成交量 |
| `amount` | 成交额 |
| `turnover_rate` | 换手率（%） |
| `turnover_rate_f` | 自由流通换手率（%） |
| `volume_ratio` | 量比 |
| `pe` | 市盈率 |
| `pe_ttm` | 滚动市盈率（TTM） |
| `pb` | 市净率 |
| `ps` | 市销率 |
| `ps_ttm` | 滚动市销率（TTM） |
| `dv_ratio` | 股息率（%） |
| `dv_ttm` | 滚动股息率（TTM） |
| `total_share` | 总股本（万股） |
| `float_share` | 流通股本（万股） |
| `free_share` | 自由流通股本（万股） |
| `total_mv` | 总市值 |
| `circ_mv` | 流通市值 |

说明：
- `daily_ohlcv` 现在同时承载基础日线行情和 `daily_basic` 扩展字段
- `pe`、`pe_ttm`、`pb`、`ps`、`ps_ttm`、`dv_ratio`、`dv_ttm` 允许合法为空
- update 完整性检查只针对必填扩展字段：`turnover_rate`、`turnover_rate_f`、`volume_ratio`、`total_share`、`float_share`、`free_share`、`total_mv`、`circ_mv`

## 3. daily_indicators

技术指标表，一只股票一个交易日一行，通常与 `daily_ohlcv` 按 `(ts_code, trade_date)` 联表使用。

| 字段 | 含义 |
| --- | --- |
| `id` | 自增主键 |
| `ts_code` | 股票代码 |
| `trade_date` | 交易日期 |
| `ma5` / `ma10` / `ma20` / `ma60` | 5、10、20、60 日均线 |
| `macd_dif` | MACD 的 DIF 线 |
| `macd_dea` | MACD 的 DEA / Signal 线 |
| `macd_hist` | MACD 柱值 |
| `rsi` | RSI 指标 |
| `kdj_k` / `kdj_d` / `kdj_j` | KDJ 三个值 |
| `cci` | CCI 顺势指标 |
| `boll_upper` / `boll_mid` / `boll_lower` | 布林带上轨、中轨、下轨 |
| `boll_width` | 布林带宽度 |
| `obv` | OBV 能量潮 |
| `mfi` | MFI 资金流量指标 |
| `vwap` | VWAP 成交量加权均价 |
| `vol_ratio` | 量比 |
| `vma20` | 20 日成交量均线 |
| `volume_multiple` | 当前成交量相对 `vma20` 的倍数 |
| `atr` | ATR 平均真实波幅 |
| `sar` | 抛物线 SAR |

## 4. rolling_scores

滚动评分结果表，主要服务于 `scripts/single_stock_rolling_score.py` 的缓存与查询。

| 字段 | 含义 |
| --- | --- |
| `id` | 自增主键 |
| `ts_code` | 股票代码 |
| `trade_date` | 评分日期 |
| `close` | 当日收盘价 |
| `next_date` | 下一交易日 |
| `change_pct` | 下一交易日涨跌幅 |
| `total_score` | 总分 |
| `trend_score` | 趋势维度得分 |
| `momentum_score` | 动量维度得分 |
| `volatility_score` | 波动维度得分 |
| `volume_score` | 成交量维度得分 |
| `pattern_score` | 形态维度得分 |
| `score_level` | 分级标签 |
| `rsi` / `mfi` / `k` / `d` / `j` / `cci` / `atr` / `volume_ratio` | 打分时保留的关键指标快照 |
| `score_details` | 评分细节，通常为文本或 JSON 字符串 |
| `signals` | 触发信号明细，通常为文本或 JSON 字符串 |
| `updated_at` | 写入更新时间 |

## 数据写入流程

1. `database/fetch_data_to_db.py` 从 Tushare 获取股票基础信息和日线行情。
2. 原始行情与 `daily_basic` 扩展字段合并后写入 `daily_ohlcv`。
3. 同批行情计算技术指标后写入 `daily_indicators`。
4. `scripts/daily_stock_scoring.py` 或 `scripts/single_stock_rolling_score.py` 基于行情和指标计算分数。
5. `database/score_repository.py` 将评分结果写入 `rolling_scores`。

## 运行模式

- `StockDatabase` 连接默认启用 `WAL`
- `synchronous` 在 `StockDatabase` 连接中设置为 `NORMAL`
- `stock_basic` 会在初始化时自动迁移到带 `ts_code PRIMARY KEY` 的结构
- `daily_ohlcv` / `daily_indicators` 不再保留与唯一约束重复的 `(ts_code, trade_date)` 显式索引

## 常用 SQL

查询所有表：

```sql
.tables
```

查询某只股票最近 10 天行情：

```sql
SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, total_mv, circ_mv
FROM daily_ohlcv
WHERE ts_code = '000001.SZ'
ORDER BY trade_date DESC
LIMIT 10;
```

查询某只股票最近 10 天技术指标：

```sql
SELECT ts_code, trade_date, ma5, ma20, macd_dif, macd_dea, rsi, mfi, atr
FROM daily_indicators
WHERE ts_code = '000001.SZ'
ORDER BY trade_date DESC
LIMIT 10;
```

联表查看行情与指标：

```sql
SELECT o.ts_code, o.trade_date, o.close, o.pct_chg,
       i.ma5, i.ma20, i.rsi, i.mfi, i.macd_dif, i.macd_dea
FROM daily_ohlcv o
LEFT JOIN daily_indicators i
  ON o.ts_code = i.ts_code AND o.trade_date = i.trade_date
WHERE o.ts_code = '000001.SZ'
ORDER BY o.trade_date DESC
LIMIT 20;
```

查询缺失 `daily_basic` 必填字段的记录：

```sql
SELECT ts_code, trade_date, turnover_rate, turnover_rate_f, volume_ratio,
       total_share, float_share, free_share, total_mv, circ_mv
FROM daily_ohlcv
WHERE turnover_rate IS NULL
   OR turnover_rate_f IS NULL
   OR volume_ratio IS NULL
   OR total_share IS NULL
   OR float_share IS NULL
   OR free_share IS NULL
   OR total_mv IS NULL
   OR circ_mv IS NULL
ORDER BY ts_code, trade_date;
```

查询某只股票评分历史：

```sql
SELECT ts_code, trade_date, total_score, trend_score, momentum_score, score_level
FROM rolling_scores
WHERE ts_code = '000001.SZ'
ORDER BY trade_date DESC;
```

查询最近一个交易日的高分股票：

```sql
SELECT ts_code, total_score, trend_score, momentum_score, volume_score, pattern_score
FROM rolling_scores
WHERE trade_date = (SELECT MAX(trade_date) FROM rolling_scores)
ORDER BY total_score DESC
LIMIT 20;
```
