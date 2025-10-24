# 专业K线图绘制工具使用说明

## 功能概述

`plot_kline.py` 是一个专业的K线图绘制工具，完全模仿真实交易软件的风格，支持展示完整的技术分析指标。

## 主要特性

### 🎨 仿交易软件界面
- ✅ **黑色背景** - 类似同花顺、东方财富等专业软件
- ✅ **经典配色** - 红涨绿跌，彩色均线
- ✅ **多指标窗口** - 主图K线、成交量、MFI、OBV分窗口显示

### 📊 技术指标展示
- ✅ **K线图** - 精确的实体和影线绘制
- ✅ **均线系统** - MA5/MA10/MA20/MA60（紫/黄/白/青）
- ✅ **成交量** - 柱状图+成交量均线
- ✅ **MFI指标** - 资金流量指数（含超买超卖区域标注）
- ✅ **OBV指标** - 能量潮+趋势判断

### 🎯 交易信号标注
- ✅ **买入信号** - 红色向上箭头 + B 标记
- ✅ **卖出信号** - 绿色向下箭头 + S 标记
- ✅ **K线形态统计** - 右上角显示锤子线、大阳线、大阴线数量

## 使用方法

### 完整工作流程

#### 1️⃣ 运行技术分析（生成数据）

```bash
# 分析单只股票，自动生成K线数据和技术指标
python technical_analysis.py --code 000001.SZ --start 20240101 --end 20241231

# 生成文件：
# - technical_analysis_000001.SZ_20241231.csv  (完整技术分析数据)
# - kline_data_000001.SZ_20241231.csv         (K线基础数据)
# - technical_analysis_000001.SZ_20241231.txt (分析日志)
```

#### 2️⃣ 绘制专业K线图

```bash
# 方法1：使用完整技术分析数据（推荐，包含所有指标）
python plot_kline.py --input technical_analysis_results/technical_analysis_000001.SZ_20241231.csv

# 方法2：使用简化K线数据（仅K线+均线，无MFI/OBV）
python plot_kline.py --input technical_analysis_results/kline_data_000001.SZ_20241231.csv

# 方法3：自定义输出路径和股票代码
python plot_kline.py \
    --input technical_analysis_results/technical_analysis_000001.SZ_20241231.csv \
    --code "平安银行(000001)" \
    --output charts/平安银行专业K线图.png
```

## 图表布局说明

```
┌─────────────────────────────────────────┐
│  主图：K线 + 均线 (MA5/10/20/60)          │  ← 3倍高度
│  - 红色K线：上涨                          │
│  - 绿色K线：下跌                          │
│  - 买卖信号标注 (B/S)                     │
│  - K线形态统计（右上角）                   │
├─────────────────────────────────────────┤
│  成交量 + 量能均线                         │  ← 1倍高度
│  - 柱状图颜色与K线一致                     │
│  - VOL_MA5/VOL_MA10                      │
├─────────────────────────────────────────┤
│  MFI 资金流量指数                         │  ← 1倍高度
│  - 超买区域 (>80) 红色标注                │
│  - 超卖区域 (<20) 绿色标注                │
│  - 当前状态提示                           │
├─────────────────────────────────────────┤
│  OBV 能量潮                              │  ← 1倍高度
│  - OBV + OBV_MA20                        │
│  - 趋势判断（上升/下降）                   │
│  - 日期轴                                │
└─────────────────────────────────────────┘
```

## 配色方案

| 元素 | 颜色 | 说明 |
|------|------|------|
| 上涨K线 | 红色 (#FF4444) | 收盘价 ≥ 开盘价 |
| 下跌K线 | 绿色 (#00CC00) | 收盘价 < 开盘价 |
| MA5 | 紫色 (#FF00FF) | 5日均线 |
| MA10 | 黄色 (#FFFF00) | 10日均线 |
| MA20 | 白色 (#FFFFFF) | 20日均线 |
| MA60 | 青色 (#00FFFF) | 60日均线 |
| MFI | 橙色 (#FFA500) | 资金流量指数 |
| OBV | 蓝色 (#4169E1) | 能量潮 |
| 背景 | 黑色 (#000000) | 仿交易软件 |
| 网格 | 深灰 (#333333) | 辅助线 |

## 技术指标说明

### MFI (Money Flow Index) - 资金流量指数
- **范围**: 0-100
- **超买**: MFI > 80（红色区域）
- **超卖**: MFI < 20（绿色区域）
- **用途**: 判断资金流入流出，辅助买卖决策

### OBV (On-Balance Volume) - 能量潮
- **计算**: 累积成交量（涨加跌减）
- **趋势**: OBV > OBV_MA20 为上升趋势
- **用途**: 确认价格趋势，判断量价配合

### 交易信号
- **买入信号 (B)**:
  - 锤子线 + 放量 + MFI超卖
  - OBV上升趋势
  - 大阳线 + 放量
  - 信号强度 ≥ 2

- **卖出信号 (S)**:
  - 射击之星 + 放量 + MFI超买
  - OBV下降趋势
  - 大阴线 + 放量
  - 信号强度 ≤ -2

## 命令参数

| 参数 | 说明 | 必需 | 默认值 |
|------|------|------|--------|
| `--input` | 输入CSV文件路径 | 是 | - |
| `--code` | 股票代码（用于标题） | 否 | 从文件名提取 |
| `--output` | 输出PNG文件路径 | 否 | 自动生成 |
| `--type` | 数据类型 (full/simple/auto) | 否 | auto |

## 输出示例

运行后生成的文件：
```
technical_analysis_results/
├── technical_analysis_000001.SZ_20241231.csv          # 完整分析数据
├── technical_analysis_000001.SZ_20241231_professional.png  # 专业K线图 ⭐
└── technical_analysis_000001.SZ_20241231.txt          # 分析日志
```

## 图表特点

### 🎯 精确绘制
- K线实体和影线精确对应OHLC数据
- 十字星特殊处理（开盘价=收盘价时）
- 日期轴与K线完美对齐

### 📈 专业指标
- 4条均线自动计算并展示
- MFI超买超卖区域高亮显示
- OBV趋势自动判断

### 🏷️ 信号标注
- 买卖信号自动标注在K线上
- K线形态统计显示在右上角
- 最新价格、涨跌幅显示在标题

### 🎨 交互友好
- 高分辨率输出（150 DPI）
- 黑色背景护眼
- 清晰的图例和标签

## 批量绘图

```bash
#!/bin/bash
# 批量分析和绘图脚本

# 股票列表
codes=("000001.SZ" "000002.SZ" "600000.SH")

for code in "${codes[@]}"; do
    echo "处理 $code ..."

    # 1. 技术分析
    python technical_analysis.py --code $code --start 20240101 --end 20241231

    # 2. 绘制K线图
    analysis_file="technical_analysis_results/technical_analysis_${code}_20241231.csv"
    if [ -f "$analysis_file" ]; then
        python plot_kline.py --input "$analysis_file" --code "$code"
    fi

    echo "完成 $code"
    echo "---"
done

echo "全部完成！"
```

## 数据要求

### 完整分析数据（推荐）
必需字段：
- `trade_date` - 交易日期
- `Open`, `High`, `Low`, `Close` - OHLC价格
- `Volume` - 成交量
- `MFI` - 资金流量指数
- `OBV`, `OBV_MA` - 能量潮及均线
- `signal`, `signal_strength` - 交易信号（可选）
- `is_hammer`, `is_big_bullish`, `is_big_bearish` - K线形态（可选）

### 简化K线数据
必需字段：
- `日期` 或 `trade_date`
- `开盘价` 或 `Open`
- `最高价` 或 `High`
- `最低价` 或 `Low`
- `收盘价` 或 `Close`
- `成交量` 或 `Volume`

## 常见问题

### Q: 图片太大/太小？
A: 修改 `plot_kline.py` 第64行：
```python
fig = plt.figure(figsize=(18, 12), ...)  # 调整宽度和高度
```

### Q: 想要更高的分辨率？
A: 修改第335行：
```python
plt.savefig(output_file, dpi=300, ...)  # 改为300或更高
```

### Q: 只想看K线和均线，不要MFI/OBV？
A: 使用简化K线数据：
```bash
python plot_kline.py --input kline_data_*.csv --type simple
```

### Q: 想要白色背景？
A: 修改第24-36行的 `COLORS` 配置：
```python
COLORS = {
    'bg': '#FFFFFF',      # 白色背景
    'text': '#000000',    # 黑色文字
    # ... 其他颜色
}
```

### Q: 日期显示不全？
A: 修改第258行：
```python
date_indices = range(0, len(df), max(1, len(df)//20))  # 增加显示数量
```

## 技术实现

### 图表库
- **matplotlib** - 专业绘图库
- **gridspec** - 灵活的子图布局
- **pandas** - 数据处理

### 绘图技术
- Rectangle patches - 精确K线实体
- plot lines - 影线和均线
- fill_between - 超买超卖区域填充
- annotate - 买卖信号箭头

### 性能优化
- 自动检测数据类型
- 智能日期轴采样
- 高效的循环绘制

## 下一步扩展

可以考虑添加：
1. MACD指标窗口
2. KDJ指标窗口
3. 布林带
4. 成交额
5. 交互式图表（plotly）
6. 导出为HTML
7. 实时数据更新

## 完整示例

```bash
# 完整的从数据获取到图表生成流程

# 1. 技术分析（包含完整指标计算）
python technical_analysis.py \
    --code 000001.SZ \
    --start 20240101 \
    --end 20241231 \
    --days 20

# 2. 查看分析结果
cat technical_analysis_results/technical_analysis_000001.SZ_20241231.txt

# 3. 绘制专业K线图
python plot_kline.py \
    --input technical_analysis_results/technical_analysis_000001.SZ_20241231.csv \
    --code "平安银行(000001.SZ)"

# 4. 查看生成的图片
# 输出: technical_analysis_results/technical_analysis_000001.SZ_20241231_professional.png
```

现在你可以获得与专业交易软件媲美的K线图表！📊✨
