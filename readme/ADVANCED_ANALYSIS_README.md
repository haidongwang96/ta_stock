# 高级技术分析工具使用说明

## 概述

`advanced_technical_analysis.py` 是一个使用 `pandas_ta` 和 `tushare` 开发的高级股票技术分析工具，实现了 `new_requirement.md` 中提到的所有主要技术指标。

## 功能特点

### 1. 趋势类指标
- **移动平均线 (MA)**：MA5, MA10, MA20, MA60
- **MACD**：包含 DIF、DEA、MACD柱，识别金叉/死叉
- **SAR**：抛物线指标，判断趋势反转点

### 2. 动量/摆荡类指标
- **RSI**：相对强弱指数，识别超买超卖
- **KDJ**：随机指标，包含K线、D线、J线
- **CCI**：商品通道指数

### 3. 波动类指标
- **布林带 (BOLL)**：上轨、中轨、下轨、带宽
- **ATR**：平均真实波幅

### 4. 成交量类指标
- **成交量分析**：量比、成交量移动平均
- **OBV**：能量潮及其趋势
- **MFI**：资金流量指数
- **VWAP**：成交量加权平均价格

### 5. 其他功能
- **支撑阻力位计算**：动态支撑位、阻力位、枢轴点
- **交易信号识别**：综合多个指标生成买卖信号
- **背离信号检测**：RSI背离、MACD背离
- **批量分析**：支持股票池批量分析

## 使用方法

### 基本用法

```bash
# 分析单个股票
python advanced_technical_analysis.py --code 000001.SZ

# 分析最近30天的数据
python advanced_technical_analysis.py --code 000001.SZ --days 30

# 指定日期范围
python advanced_technical_analysis.py --code 000001.SZ --start 20250901 --end 20251028
```

### 批量分析

```bash
# 从股票池文件读取第一个股票
python advanced_technical_analysis.py --pool stock_pool.txt

# 批量分析股票池中的所有股票
python advanced_technical_analysis.py --pool stock_pool.txt --batch
```

### 使用Shell脚本

```bash
# 使用便利脚本分析单个股票
./run_advanced_analysis.sh -c 000001.SZ

# 批量分析
./run_advanced_analysis.sh -p stock_pool.txt -b

# 查看帮助
./run_advanced_analysis.sh -h
```

## 参数说明

- `--code`：股票代码（如 000001.SZ）
- `--pool`：股票池文件路径
- `--batch`：批量分析模式
- `--days`：分析最近N天的数据（默认120天）
- `--start`：开始日期 YYYYMMDD
- `--end`：结束日期 YYYYMMDD
- `--report_days`：报告中显示最近N天的信号（默认20天）
- `--output`：输出文件名

## 输出文件

所有分析结果保存在 `advanced_analysis_results/` 文件夹中：

- `advanced_analysis_[股票代码].csv`：详细分析数据
- `batch_analysis_summary.csv`：批量分析汇总报告

## 股票池文件格式

```
# 股票池文件示例
# 格式：股票代码#股票名称（名称可选）

000001.SZ#平安银行
000002.SZ#万科A
000858.SZ#五粮液
002415.SZ#海康威视
600036.SH#招商银行
```

## 分析报告内容

### 1. 价格概况
- 最新收盘价和日涨跌幅
- 短期趋势（MA5 vs MA20）
- 中期趋势（MA20 vs MA60）

### 2. 技术指标状态
- RSI、KDJ、CCI 当前值和状态
- MACD 多空状态和位置
- 布林带位置和带宽
- 成交量分析和OBV趋势

### 3. 交易信号
- 买入信号：金叉、超卖反弹、放量突破等
- 卖出信号：死叉、超买回落、放量下跌等
- 信号强度评级：强、中、弱

### 4. 综合建议
- 根据信号强度给出操作建议
- 强度 >= 5：强烈买入
- 强度 >= 3：买入
- 强度 <= -5：强烈卖出
- 强度 <= -3：卖出
- 其他：观望

## 注意事项

1. 需要安装依赖：`pandas`, `pandas_ta`, `tushare`, `numpy`
2. 需要有效的 Tushare token（已内置）
3. 技术指标仅供参考，不构成投资建议
4. 建议结合基本面分析和市场环境综合判断

## 与原脚本的对比

| 功能 | technical_analysis.py | advanced_technical_analysis.py |
|------|----------------------|--------------------------------|
| 指标数量 | 较少（MFI、OBV等） | 全面（包含所有主流指标） |
| 趋势指标 | 基础 | 完整（MA、MACD、SAR） |
| 动量指标 | 无 | 完整（RSI、KDJ、CCI） |
| 波动指标 | 无 | 完整（布林带、ATR） |
| 信号识别 | 简单 | 复杂（多指标综合） |
| 背离检测 | 无 | 有（RSI、MACD背离） |
| 批量分析 | 有限 | 完整支持 |
| 报告输出 | 基础 | 详细综合分析 |

## 更新日志

- 2025-10-28：初始版本发布
  - 实现所有主要技术指标
  - 支持批量分析
  - 添加综合信号识别
  - 添加背离检测功能