# daily_stock_scoring.py 使用说明

## 概述

`daily_stock_scoring.py` 是一个股票当日技术面打分排名系统，基于 `advanced_technical_analysis.py` 的完整打分规则，对股票池中的股票进行批量分析，按技术面综合得分排序输出。

## 核心特性

### 1. 完整的打分系统
- **5大类技术指标打分**：趋势类、动量类、波动类、成交量类、形态类
- **30+项打分规则**：涵盖MACD、SAR、均线、RSI、KDJ、CCI、布林带、ATR、MFI、OBV、VWAP、K线形态、背离、支撑阻力等
- **打分等级**：强烈看多(≥8) / 看多(5~7) / 偏多(2~4) / 中性(-1~1) / 偏空(-4~-2) / 看空(-7~-5) / 强烈看空(≤-8)

### 2. 多进程并发
- 使用 `ProcessPoolExecutor` 并发处理多只股票
- 可自定义并发进程数（默认4）
- 显著提升批量分析速度

### 3. 详细报告输出
- **TXT详细报告**：包含综合排行榜、分项统计、信号分析、综合建议
- **CSV数据汇总**：包含所有打分数据和关键指标，便于二次分析

## 安装依赖

```bash
pip install pandas pandas_ta tushare numpy
```

## 命令行参数

```bash
python daily_stock_scoring.py --pool <股票池文件> [选项]
```

### 参数说明

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `--pool` | ✅ | - | 股票池文件路径 |
| `--days` | ❌ | 60 | 获取历史数据天数 |
| `--workers` | ❌ | 4 | 并发进程数 |
| `--output_dir` | ❌ | daily_scoring_results | 输出目录 |

## 使用示例

### 基本用法
```bash
python daily_stock_scoring.py --pool stock_pool_small.txt
```

### 自定义参数
```bash
python daily_stock_scoring.py --pool stock_pool_small.txt --days 90 --workers 8
```

### 指定输出目录
```bash
python daily_stock_scoring.py --pool my_stocks.txt --output_dir my_results
```

## 股票池文件格式

支持以下格式：

```
# 注释行
股票代码1  # 行内注释
股票代码2

# 示例
688256.SH  # 寒武纪
603893.SH  # 瑞芯微
000001.SZ  # 平安银行
```

- 每行一个股票代码
- 支持 `#` 开头的注释行
- 支持行内注释（`代码 # 名称`）
- 空行会被忽略

## 输出文件

### 1. TXT详细报告

**文件名**: `daily_scoring_report_YYYYMMDD_HHMMSS.txt`

**内容结构**：

#### 📊 综合得分排行榜 TOP 30
显示总分最高的30只股票：
```
排名    股票代码        总分      收盘价       涨跌幅       MFI     关键信号
----------------------------------------------------------------------------------------------------
1     300475.SZ       +4    128.31    -4.00%    56.9  MACD红柱增长(+1); 均线多头排列(+3)...
2     688256.SH       +3   1478.58    -3.40%    64.4  均线多头排列(+3); CCI强势(+1)...
```

#### 📈 分项得分统计
5大类指标的平均分、最高分、最低分及对应股票：
```
趋势类得分:
  平均分: +1.62
  最高分: +4 (603986.SH)
  最低分: -3 (603893.SH)
```

#### 🔥 强烈看多/看空股票
- **强烈看多** (总分≥8)：显示股票代码、总分、价格、涨跌幅、分项得分、打分明细
- **强烈看空** (总分<-7)：同上

#### 📊 趋势类高分股票 TOP 10
趋势类得分≥5的股票列表

#### 🎯 RSI超卖/超买股票
- RSI < 30：超卖股票
- RSI > 70：超买股票

#### 💰 MFI超卖/超买股票
- MFI < 30：超卖股票
- MFI > 70：超买股票

#### 📊 放量股票
量比 > 1.5 的股票列表，按量比排序

#### 📈 OBV趋势统计
OBV上升/下降趋势的股票数量和占比

#### 💡 综合建议
按打分等级分组推荐关注股票

### 2. CSV数据汇总

**文件名**: `daily_scoring_summary_YYYYMMDD_HHMMSS.csv`

**列说明**：

| 列名 | 说明 |
|------|------|
| rank | 排名 |
| code | 股票代码 |
| date | 分析日期 |
| close | 收盘价 |
| change_pct | 涨跌幅(%) |
| total_score | 总分 |
| trend_score | 趋势类得分 |
| momentum_score | 动量类得分 |
| volatility_score | 波动类得分 |
| volume_score | 成交量类得分 |
| pattern_score | 形态类得分 |
| score_details | 打分明细 |
| mfi | MFI指标值 |
| rsi | RSI指标值 |
| volume_ratio | 量比 |
| obv_trend | OBV趋势(up/down) |
| score_level | 打分等级 |

**用途**：
- 可导入Excel进行二次分析
- 可用Python/pandas进行数据分析
- 可用于量化策略回测

## 打分规则详解

### 趋势类打分 (Trend Score)

| 信号 | 条件 | 得分 |
|------|------|------|
| MACD低位金叉 | DIF上穿DEA且在0轴下方 | +3 |
| MACD金叉 | DIF上穿DEA且在0轴上方 | +2 |
| MACD高位死叉 | DIF下穿DEA且在0轴上方 | -3 |
| MACD死叉 | DIF下穿DEA且在0轴下方 | -2 |
| MACD红柱增长 | 柱状图>0且增长 | +1 |
| MACD绿柱增长 | 柱状图<0且减小 | -1 |
| SAR空转多 | 从空头转为多头 | +3 |
| SAR多转空 | 从多头转为空头 | -3 |
| SAR多头持续 | 持续多头 | +2 |
| SAR空头持续 | 持续空头 | -2 |
| 均线多头排列 | Close>MA5>MA10>MA20 | +3 |
| 均线空头排列 | Close<MA5<MA10<MA20 | -3 |

### 动量类打分 (Momentum Score)

| 信号 | 条件 | 得分 |
|------|------|------|
| RSI严重超卖 | RSI < 20 | +3 |
| RSI超卖 | 20 ≤ RSI < 30 | +2 |
| RSI严重超买 | RSI > 80 | -3 |
| RSI超买 | 70 < RSI ≤ 80 | -2 |
| RSI突破中轴 | RSI上穿50 | +1 |
| RSI跌破中轴 | RSI下穿50 | -1 |
| KDJ低位金叉 | K上穿D且D<20 | +3 |
| KDJ高位死叉 | K下穿D且D>80 | -3 |
| J值极度超卖 | J < 0 | +2 |
| J值极度超买 | J > 100 | -2 |
| CCI脱离超卖区 | CCI上穿-100 | +2 |
| CCI脱离超买区 | CCI下穿100 | -2 |
| CCI强势 | CCI > 100 | +1 |
| CCI弱势 | CCI < -100 | -1 |

### 波动类打分 (Volatility Score)

| 信号 | 条件 | 得分 |
|------|------|------|
| 突破布林上轨 | Close > BOLL_Upper | -2 |
| 突破布林下轨 | Close < BOLL_Lower | +2 |
| 触及布林上轨 | Close ≥ BOLL_Upper*0.98 | -1 |
| 触及布林下轨 | Close ≤ BOLL_Lower*1.02 | +1 |
| 布林带开口上涨 | 带宽增大且价格上涨 | +1 |
| 布林带开口下跌 | 带宽增大且价格下跌 | -1 |
| ATR波动加大上涨 | ATR>均值*1.5且上涨 | +1 |
| ATR波动加大下跌 | ATR>均值*1.5且下跌 | -2 |

### 成交量类打分 (Volume Score)

| 信号 | 条件 | 得分 |
|------|------|------|
| 价格远高于VWAP | Close > VWAP*1.02 | +2 |
| 价格高于VWAP | Close > VWAP | +1 |
| 价格远低于VWAP | Close < VWAP*0.98 | -2 |
| 价格低于VWAP | Close < VWAP | -1 |
| MFI严重超卖 | MFI < 10 | +3 |
| MFI超卖 | 10 ≤ MFI < 20 | +2 |
| MFI严重超买 | MFI > 90 | -3 |
| MFI超买 | 80 < MFI ≤ 90 | -2 |
| OBV上升趋势 | OBV > OBV_MA | +2 |
| OBV下降趋势 | OBV < OBV_MA | -2 |
| 放量上涨 | Volume_Ratio>1.5且上涨 | +2 |
| 放量下跌 | Volume_Ratio>1.5且下跌 | -2 |
| MFI超卖+OBV上升 | MFI<20且OBV上升 | +2 |
| MFI超买+OBV下降 | MFI>80且OBV下降 | -2 |

### 形态类打分 (Pattern Score)

| 信号 | 条件 | 得分 |
|------|------|------|
| RSI底背离 | 价格新低但RSI不创新低 | +3 |
| RSI顶背离 | 价格新高但RSI不创新高 | -3 |
| MACD底背离 | 价格新低但MACD不创新低 | +3 |
| MACD顶背离 | 价格新高但MACD不创新高 | -3 |
| 突破阻力位 | 价格突破阻力位 | +3 |
| 跌破支撑位 | 价格跌破支撑位 | -3 |
| 获得支撑 | 低点触及支撑但收盘在上方 | +2 |
| 遇到阻力 | 高点触及阻力但收盘在下方 | -2 |
| 锤子线 | 下影线>实体*2且在下跌趋势后 | +3 |
| 射击之星 | 上影线>实体*2且在上涨趋势后 | -3 |
| 大阳线 | 实体比例>0.7 | +2 |
| 大阴线 | 实体比例>0.7 | -2 |

## 性能优化建议

### 1. 调整并发进程数

根据CPU核心数调整：
```bash
# 4核CPU
python daily_stock_scoring.py --pool stocks.txt --workers 4

# 8核CPU
python daily_stock_scoring.py --pool stocks.txt --workers 8
```

### 2. 调整历史数据天数

- 最少建议60天（确保指标计算准确）
- 可根据需要增加到90天或120天
- 天数越多，数据获取时间越长

```bash
# 使用90天数据
python daily_stock_scoring.py --pool stocks.txt --days 90
```

### 3. 注意API限流

Tushare API有调用频率限制：
- 免费用户：每分钟200次
- 如果股票池较大，可能触发限流
- 建议减少并发进程数或分批处理

## 常见问题

### Q1: 出现 "VWAP requires an ordered DatetimeIndex" 警告

**答**：这是pandas_ta库的已知警告，不影响功能，可以忽略。

### Q2: 部分股票分析失败

**答**：可能原因：
- 股票代码错误
- 该股票在指定日期范围内无数据（如新股、停牌）
- API调用失败

查看日志中的 `✗` 标记了解失败原因。

### Q3: 速度较慢

**答**：优化方法：
1. 增加并发进程数 `--workers 8`
2. 减少历史数据天数 `--days 60`
3. 分批处理大股票池

### Q4: 如何理解打分结果

**答**：
- **总分≥5**：技术面看多，可关注
- **总分≥8**：技术面强烈看多，重点关注
- **总分≤-5**：技术面看空，谨慎
- **-1≤总分≤1**：技术面中性，观望

结合分项得分和打分明细分析：
- 趋势类得分高：趋势向好
- 动量类得分低但其他得分高：可能是超卖反弹机会
- 查看 `score_details` 了解具体信号

## 与其他脚本的对比

| 特性 | daily_stock_scoring.py | batch_technical_analysis.py | advanced_technical_analysis.py |
|------|----------------------|----------------------------|------------------------------|
| 打分系统 | ✅ 完整5大类打分 | ⚠️ 简化打分 | ✅ 完整5大类打分 |
| 批量分析 | ✅ 支持 | ✅ 支持 | ❌ 仅单股 |
| 多进程 | ✅ 支持 | ✅ 支持 | ❌ 单进程 |
| 详细报告 | ✅ 详细版 | ✅ 简洁版 | ✅ 超详细版 |
| 单股日志 | ❌ 不生成 | ❌ 不生成 | ✅ 生成 |
| CSV输出 | ✅ 汇总CSV | ✅ 汇总CSV | ✅ 单股CSV |
| 适用场景 | 批量打分排序 | 快速批量浏览 | 单股深度分析 |

**选择建议**：
- **批量打分选股**：使用 `daily_stock_scoring.py`
- **快速批量浏览**：使用 `batch_technical_analysis.py`
- **单股深度分析**：使用 `advanced_technical_analysis.py`

## 使用流程建议

1. **批量打分**：用 `daily_stock_scoring.py` 对股票池打分
2. **筛选高分股**：从CSV中筛选总分≥5的股票
3. **深度分析**：用 `advanced_technical_analysis.py` 对筛选出的股票进行深度分析
4. **决策交易**：结合基本面和其他因素做出交易决策

## 更新历史

- **v1.0** (2025-10-29)
  - 初始版本发布
  - 完整的5大类打分系统
  - 多进程并发支持
  - 详细版报告输出

## 相关文档

- [new_requirement.md](new_requirement.md) - 技术指标需求文档
- [SCORING_UPDATE.md](SCORING_UPDATE.md) - 打分系统更新说明
- [FEATURE_UPDATE_20251028.md](FEATURE_UPDATE_20251028.md) - 功能更新记录

---

**作者**: AI Assistant
**创建日期**: 2025-10-29
**版本**: v1.0
