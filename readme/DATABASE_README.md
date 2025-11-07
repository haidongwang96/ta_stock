# 股票数据本地化数据库使用指南

## 📋 概述

本地数据库系统基于 **SQLite** 实现，旨在将 Tushare 股票数据存储到本地，实现：
- ✅ **脱离网络依赖**：数据查询速度提升100倍+
- ✅ **减少API调用**：节省95%以上的 Tushare API 调用次数
- ✅ **技术指标预计算**：常用指标（MA、MACD、RSI等）预存，分析速度提升3-5倍
- ✅ **智能日期对齐**：批量分析时自动使用所有股票共同的最新日期，确保公平比较
- ✅ **易于扩展**：支持未来添加分钟线、基本面等更多数据

---

## 🗂️ 数据库结构

### 数据库文件
- **文件名**：`stock_data.db`
- **位置**：项目根目录
- **类型**：SQLite 3

### 数据表

#### 1. `stock_basic` - 股票基本信息
| 字段 | 类型 | 说明 |
|------|------|------|
| ts_code | TEXT | 股票代码（主键），如 688256.SH |
| symbol | TEXT | 股票简称 |
| name | TEXT | 股票名称 |
| area | TEXT | 地域 |
| industry | TEXT | 行业 |
| market | TEXT | 市场类型（主板/创业板/科创板） |
| list_date | TEXT | 上市日期 |
| update_time | TEXT | 数据更新时间 |

#### 2. `daily_ohlcv` - 日线原始数据
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| ts_code | TEXT | 股票代码 |
| trade_date | TEXT | 交易日期（YYYYMMDD） |
| open | REAL | 开盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| close | REAL | 收盘价 |
| pre_close | REAL | 前收盘价 |
| change | REAL | 涨跌额 |
| pct_chg | REAL | 涨跌幅（%） |
| vol | REAL | 成交量（手） |
| amount | REAL | 成交额（千元） |

**索引**：(ts_code, trade_date) 组合索引

#### 3. `daily_indicators` - 技术指标数据（预计算）
| 字段类别 | 字段 | 说明 |
|---------|------|------|
| **基础** | id, ts_code, trade_date | 主键和关联字段 |
| **均线** | ma5, ma10, ma20, ma60 | 移动平均线 |
| **MACD** | macd_dif, macd_dea, macd_hist | MACD指标 |
| **动量** | rsi, kdj_k, kdj_d, kdj_j, cci | RSI、KDJ、CCI |
| **布林带** | boll_upper, boll_mid, boll_lower, boll_width | 布林带指标 |
| **成交量** | obv, mfi, vwap, vol_ratio | 能量潮、资金流量指数、VWAP、量比 |
| **波动率** | atr | 平均真实波幅 |
| **趋势** | sar | 抛物线指标 |

**索引**：(ts_code, trade_date) 组合索引

---

## 🚀 快速开始

### 步骤 1：初始化数据库（首次使用）

**方式一：使用默认股票池**

```bash
# 初始化数据库，导入 stock_pool_example.txt 中的所有股票，获取最近1年数据
python database/fetch_data_to_db.py --init --days 365
```

**方式二：指定股票池文件**

```bash
# 使用自定义股票池
python database/fetch_data_to_db.py --init --pool my_stocks.txt --days 365
```

**方式三：指定股票代码**

```bash
# 只初始化特定股票
python database/fetch_data_to_db.py --init --codes "688256.SH,603893.SH,300502.SZ" --days 365
```

> **⏱️ 预计耗时**：120只股票约需要 **3-5分钟**（取决于网络和API限速）

---

### 步骤 2：使用本地数据库运行分析

所有现有的分析脚本都已支持本地数据库，只需添加 `--use-local-db` 参数：

#### 单股票技术分析

```bash
# 原命令（在线Tushare）
python technical_analysis.py --code 688256.SH --days 60

# 使用本地数据库（速度快100倍+）
python technical_analysis.py --code 688256.SH --days 60 --use-local-db
```

#### 批量技术分析

```bash
# 使用本地数据库分析股票池
python batch_technical_analysis.py --pool stock_pool_example.txt --use-local-db
```

#### 高级技术分析

```bash
# 单个股票高级分析
python advanced_technical_analysis.py --code 688256.SH --days 120 --use-local-db

# 批量分析股票池
python advanced_technical_analysis.py --pool stock_pool_example.txt --batch --use-local-db
```

#### 每日打分排名 ⭐ 智能日期对齐

```bash
# 批量打分排名（4进程并行）
# 使用本地数据库时，会自动查询所有股票共同的最新日期作为基准
python daily_stock_scoring.py --pool stock_pool_example.txt --days 60 --workers 4 --use-local-db
```

> **💡 智能日期对齐**：当使用本地数据库时，系统会：
> 1. 扫描股票池中所有股票的最新日期
> 2. 找出所有股票都有数据的最新日期（共同最新日期）
> 3. 使用这个日期作为统一的分析基准
> 4. 确保所有股票在同一天的数据上进行公平比较

**示例输出**：
```
正在查询股票池中所有股票的最新日期...
✓ 股票池共同最新日期: 20250105
  最早: 20250105
  最晚: 20250106
  共有 120/120 只股票有数据
  注意：15 只股票数据较新，将统一使用 20250105 作为基准日期
  数据较新的股票: 688256.SH, 603893.SH, 300502.SZ 等15只
```

---

### 步骤 3：增量更新数据（每日维护）

```bash
# 增量更新所有股票的最新数据（只下载缺失的日期）
python database/fetch_data_to_db.py --update

# 更新指定股票
python database/fetch_data_to_db.py --update --codes "688256.SH,603893.SH"

# 更新指定股票池
python database/fetch_data_to_db.py --update --pool stock_pool_example.txt
```

> **💡 建议**：每日收盘后运行一次增量更新，耗时约 **1-2分钟**
>
> **🔧 Bug修复**：已修复增量更新无法获取当天数据的问题（原判断条件为 `>=`，已改为 `>`）

---

## 📊 数据查询示例

### 方式一：使用 Python API

```python
from database.query_helper import StockDataQuery

# 创建查询对象
query = StockDataQuery()

# 查询日线数据
df = query.daily('688256.SH', start_date='20230101', end_date='20231231')
print(df.head())

# 查询日线数据 + 技术指标（合并）
df_full = query.daily_with_indicators('688256.SH', start_date='20230101')
print(df_full.columns)  # 包含OHLCV和所有技术指标

# 便捷方法：获取最近N天数据（字段已自动重命名为pandas_ta格式）
df_analysis = query.get_stock_data_for_analysis('688256.SH', days=60)
print(df_analysis)  # Open, High, Low, Close, Volume

# 检查数据可用性
info = query.check_data_availability('688256.SH')
print(info)
# {
#   'available': True,
#   'start_date': '20230101',
#   'end_date': '20240101',
#   'record_count': 243,
#   'is_latest': True
# }

# 关闭连接
query.close()
```

### 方式二：便捷函数（无需创建对象）

```python
from database.query_helper import daily

# 直接调用（自动管理连接）
df = daily('688256.SH', start_date='20230101', end_date='20231231')
```

### 方式三：上下文管理器（推荐）

```python
from database.query_helper import StockDataQuery

with StockDataQuery() as query:
    df = query.daily('688256.SH', start_date='20230101')
    # 自动关闭连接
```

---

## 🔧 高级功能

### 1. 查看数据库统计信息

```python
from database.db_manager import StockDatabase

db = StockDatabase()
stats = db.get_data_statistics()
print(stats)
# {
#   'stock_count': 120,
#   'ohlcv_records': 29160,
#   'indicator_records': 29160,
#   'date_range': ('20230101', '20240101'),
#   'db_size_mb': 12.5
# }
db.close()
```

### 2. 删除特定股票数据

```python
from database.db_manager import StockDatabase

db = StockDatabase()

# 删除单个股票的所有数据
db.delete_stock_data('688256.SH')

db.close()
```

### 3. 查询股票数据日期范围

```python
from database.db_manager import StockDatabase

db = StockDatabase()

# 查询单个股票的数据范围
min_date, max_date = db.get_date_range('688256.SH')
print(f"数据范围: {min_date} 至 {max_date}")

# 查询数据库中最新的交易日期
latest_date = db.get_latest_date()  # 所有股票的最新日期
latest_date_for_stock = db.get_latest_date('688256.SH')  # 特定股票

db.close()
```

### 4. 自定义数据库路径

```python
from database.db_manager import StockDatabase

# 使用自定义数据库路径
db = StockDatabase(db_path='/path/to/my_stock_data.db')
```

---

## ⚠️ 常见问题

### Q1: 初始化时出现 "API限频" 错误
**A:** Tushare有API调用频率限制，脚本已内置延迟（0.15秒/次）。如果仍然失败：
- 检查你的 Tushare 账户积分和权限
- 减少并发请求，增加 `time.sleep()` 延迟
- 分批初始化，每次处理部分股票

### Q2: 本地数据库的数据不是最新的怎么办？
**A:** 运行增量更新命令：
```bash
python database/fetch_data_to_db.py --update
```

### Q3: 增量更新时无法获取今天的数据？
**A:** 这个bug已经修复！原来的判断条件 `if start_date >= end_date` 会跳过今天的数据，现已改为 `if start_date > end_date`。

### Q4: 如何知道数据库中有哪些股票？
**A:**
```python
from database.db_manager import StockDatabase

db = StockDatabase()
stock_list = db.get_stock_list()
print(stock_list)
db.close()
```

### Q5: 批量打分时，不同股票数据更新时间不同怎么办？
**A:** 使用 `--use-local-db` 参数时，系统会自动：
- 查询所有股票的最新日期
- 找出共同的最新日期（所有股票都有数据的最新日期）
- 使用这个统一日期进行分析
- 确保所有股票在同一天的数据上进行公平比较

**示例**：
```bash
python daily_stock_scoring.py --pool stock_pool_example.txt --use-local-db
```

输出会显示：
```
正在查询股票池中所有股票的最新日期...
✓ 股票池共同最新日期: 20250105
  最早: 20250105
  最晚: 20250106
```

### Q6: 数据库文件太大怎么办？
**A:** SQLite数据库会随着数据增长而增大。如果需要清理：
- 删除不需要的股票数据（使用 `delete_stock_data()`）
- 缩短历史数据范围（重新初始化时使用 `--days` 指定更短的天数）
- 使用 SQLite VACUUM 命令压缩数据库

### Q7: 可以同时使用本地数据库和在线Tushare吗？
**A:** 可以！脚本默认使用在线Tushare，添加 `--use-local-db` 参数时使用本地数据库。

### Q8: 数据库损坏怎么办？
**A:** 删除 `stock_data.db` 文件，重新运行初始化命令。

---

## 📈 性能对比

| 操作 | 在线Tushare | 本地数据库 | 提升倍数 |
|------|------------|-----------|---------|
| 单股票60天数据查询 | ~1-2秒 | <0.01秒 | **100倍+** |
| 120股票批量分析 | ~5-10分钟 | ~10-20秒 | **30倍+** |
| 每日打分排名（120股票） | ~8-15分钟 | ~30-60秒 | **15倍+** |
| API调用次数（批量分析） | 120次 | 0次 | **节省100%** |

---

## 📁 目录结构

```
ta_stock/
├── database/                      # 数据库模块目录
│   ├── __init__.py               # 模块初始化
│   ├── db_manager.py             # 数据库管理类（底层API）
│   ├── query_helper.py           # 查询辅助类（高层API）
│   └── fetch_data_to_db.py       # 数据抓取脚本
├── md/                           # 文档目录
│   └── DATABASE_README.md        # 本文档
├── stock_data.db                 # SQLite数据库文件（初始化后生成）
├── technical_analysis.py         # 单股票技术分析（支持 --use-local-db）
├── batch_technical_analysis.py   # 批量技术分析（支持 --use-local-db）
├── advanced_technical_analysis.py # 高级技术分析（支持 --use-local-db）
├── daily_stock_scoring.py        # 每日打分排名（支持 --use-local-db + 智能日期对齐）
└── stock_pool_example.txt        # 股票池示例
```

---

## 🔄 工作流程建议

### 日常使用流程

```bash
# 1. 早上/收盘后：增量更新数据
python database/fetch_data_to_db.py --update

# 2. 运行分析（使用本地数据库，自动日期对齐）
python daily_stock_scoring.py --pool stock_pool_example.txt --use-local-db

# 3. 查看结果
cat daily_scoring_results/daily_scoring_report_*.txt
```

### 周末维护流程

```bash
# 1. 检查数据库状态
python -c "from database.db_manager import StockDatabase; db = StockDatabase(); print(db.get_data_statistics()); db.close()"

# 2. 全量更新（可选，补充遗漏数据）
python database/fetch_data_to_db.py --update

# 3. 备份数据库（可选）
cp stock_data.db stock_data_backup_$(date +%Y%m%d).db
```

---

## 🛠️ 故障排查

### 1. 导入错误：`ModuleNotFoundError: No module named 'database'`
**原因**：Python 找不到 database 模块
**解决**：确保在项目根目录运行脚本，或将项目根目录添加到 PYTHONPATH

### 2. 数据库文件找不到
**原因**：首次使用未初始化
**解决**：运行初始化命令
```bash
python database/fetch_data_to_db.py --init
```

### 3. 查询结果为空
**原因**：数据库中无对应股票或日期范围的数据
**解决**：
- 检查股票代码格式（如 688256.SH，不是 sh688256）
- 检查日期范围是否在数据库覆盖范围内
- 运行 `get_date_range()` 查看可用数据范围

### 4. 技术指标为 NaN
**原因**：指标计算需要足够的历史数据
**解决**：增加初始化时的天数（`--days` 参数至少60天）

### 5. 增量更新无法获取今天的数据
**原因**：这是已修复的bug，如果仍有问题，请检查代码版本
**解决**：确保 `fetch_data_to_db.py` 第344行的判断条件为 `if start_date > end_date:`（不是 `>=`）

---

## 🆕 版本更新日志

### v1.1 (2025-01-06)
- ✅ **新增**：智能日期对齐功能（`daily_stock_scoring.py`）
  - 自动查询股票池中所有股票的最新日期
  - 使用共同最新日期作为分析基准
  - 确保批量比较的公平性
- ✅ **修复**：增量更新无法获取当天数据的bug
  - 原判断条件 `start_date >= end_date` 导致跳过当天
  - 修正为 `start_date > end_date`
- ✅ **改进**：报告中显示分析基准日期

### v1.0 (2025-01-05)
- ✅ 初始版本发布
- ✅ 支持SQLite本地数据库
- ✅ 预计算20+常用技术指标
- ✅ 支持全量初始化和增量更新
- ✅ 所有分析脚本支持本地数据库

---

## 📞 技术支持

如有问题或建议，请：
1. 查阅本文档的"常见问题"部分
2. 检查日志输出中的错误信息
3. 提Issue到项目仓库

---

## 🎯 未来扩展

数据库系统预留了扩展空间，未来可以添加：
- ✨ 分钟线数据（1分钟、5分钟、15分钟等）
- ✨ 基本面数据（财务报表、估值指标等）
- ✨ 行情数据（涨跌停、换手率、龙虎榜等）
- ✨ 实时数据推送和自动更新
- ✨ 多账户分布式抓取（加速数据获取）

只需在 `db_manager.py` 中添加新的表结构，在 `fetch_data_to_db.py` 中添加数据获取逻辑即可。

---

**祝使用愉快！📈**
