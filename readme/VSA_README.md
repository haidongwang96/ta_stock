sc
## 📚 概述

本框架基于 `duanxian.md` 文档实现了纯量价分析（VSA - Volume Spread Analysis）的短线交易系统。

**核心理念**：抛弃所有滞后指标（如MACD、KDJ、MA），仅通过Price和Volume的原始关系，捕捉市场主力资金的真实意图。

## 🏗️ 框架结构

```
ta_stock/
├── analysis/                    # 分析模块
│   ├── vsa_signals.py          # VSA原子信号检测器
│   └── market_structure.py     # 市场结构分析器
│
├── strategies/                  # 策略模块
│   └── vsa_strategy.py         # VSA右侧买入策略
│
├── config/                      # 配置文件
│   └── vsa_config.py           # VSA参数配置
│
├── scripts/                     # 脚本工具
│   ├── vsa_scanner.py          # VSA扫描器（主程序）
│   └── daily_stock_scoring.py  # 综合评分系统（已集成VSA）
│
├── database/                    # 数据库模块
│   ├── db_manager.py           # 数据库管理（已添加VMA字段）
│   └── fetch_data_to_db.py     # 数据抓取（已添加VMA计算）
│
└── test_vsa_framework.py       # 测试脚本
```

## 🎯 VSA核心概念

### 1. 六种原子信号

| 信号类型 | 描述 | 含义 | 得分 |
|---------|------|------|------|
| **HEALTHY_UP** | 价涨量增 | 健康上涨，需求强劲 | +1~+3 |
| **WEAK_UP** | 价涨量缩 | 无量空涨，警告信号 | -1 |
| **PANIC_SELL** | 价跌量增 | 恐慌抛售，供应强劲 | -1~-3 |
| **SUPPLY_DRY_UP** | 价跌量缩 | 供应枯竭，关键买入信号 | +2~+3 |
| **ABSORPTION_BAR** | 价平量增 | 吸筹/派发，双方激战 | 0 |
| **NO_INTEREST** | 价平量缩 | 市场观望 | 0 |

### 2. 四种市场结构

- **ACCUMULATION**（吸筹区）：底部横盘，主力悄悄买入
- **MARK_UP**（上涨区）：趋势向上，**这是我们要找入场的阶段**
- **DISTRIBUTION**（派发区）：顶部横盘，主力悄悄卖出
- **MARK_DOWN**（下跌区）：趋势向下

### 3. 三种右侧买入策略

#### 策略1：缩量回调后需求确认（TEST_ENTRY）
- 前期有过上涨（价涨量增）
- 最近2-3天缩量回调（价跌量缩）
- 今天出现放量阳线（需求回归）

#### 策略2：突破-回踩（BREAKOUT_PULLBACK）
- 放量突破20日高点
- 回踩到支撑位附近
- 回踩时缩量企稳
- 出现拐头向上

#### 策略3：恐慌抛售后吸筹确认（SELLING_CLIMAX）
- 出现恐慌抛售（长下影线+天量）
- 之后不再创新低
- 成交量迅速萎缩
- 价格开始回升

## 🚀 快速开始

### 1. 更新数据库（计算VMA）

首次使用需要更新数据库，为所有股票计算VMA指标：

```bash
# 更新所有股票的VMA数据
python database/fetch_data_to_db.py --update

# 或者只更新特定股票
python database/fetch_data_to_db.py --code 600519.SH
```

### 2. 运行VSA扫描器

#### 扫描股票池

创建股票池文件 `my_stocks.txt`：
```
600519.SH  # 贵州茅台
000858.SZ  # 五粮液
601318.SH  # 中国平安
```

运行扫描：
```bash
python scripts/vsa_scanner.py --pool my_stocks.txt
```

#### 扫描单只股票

```bash
python scripts/vsa_scanner.py --code 600519.SH
```

#### 保存结果到CSV

```bash
python scripts/vsa_scanner.py --pool my_stocks.txt --output vsa_signals.csv
```

### 3. 查看综合评分报告（包含VSA）

原有的评分系统已集成VSA评分：

```bash
# 使用本地数据库
python scripts/daily_stock_scoring.py --db

# 指定股票池
python scripts/daily_stock_scoring.py --db --stock-pool my_stocks.txt
```

评分报告中会新增：
- `VSA_Score` 列：VSA量价分析得分
- `VSA_Signal` 列：VSA信号类型

## 📊 输出示例

### VSA扫描器输出

```
发现 2 个入场信号:

ts_code    name    latest_price  type                price  strength  description               stop_loss  target
600519.SH  贵州茅台  1680.50      TEST_ENTRY          1680   3         缩量回调后需求确认(回调3天)  1650.00   1764.00
000858.SZ  五粮液   185.20       BREAKOUT_PULLBACK   185    2         突破182.50后回踩确认        179.25    199.92
```

### 综合评分报告

```
综合得分排行榜:
排名  股票代码    总分  VSA得分  VSA信号              关键信号
1     600519.SH  +15   +3      价跌量缩-供应枯竭     MACD金叉; RSI超卖; 缩量回调
2     000858.SZ  +12   +2      价涨量增-健康上涨     突破阻力位; OBV上升
```

## ⚙️ 参数配置

所有参数集中在 `config/vsa_config.py`，可根据需要调整：

### 信号检测参数
```python
VSA_SIGNAL_PARAMS = {
    'volume_high_threshold': 1.5,    # 放量标准：>1.5倍VMA
    'volume_low_threshold': 1.0,     # 缩量标准：<1.0倍VMA
    'narrow_range_pct': 0.02,        # 窄幅阈值：2%
}
```

### 策略参数
```python
STRATEGY_PARAMS = {
    'test_entry': {
        'pullback_days': 3,              # 回调天数
        'min_supply_dry_count': 2,       # 最少缩量回调天数
        'profit_target_pct': 0.05,       # 目标涨幅5%
    },
    # ...
}
```

## 🧪 测试框架

运行测试脚本验证框架功能：

```bash
python test_vsa_framework.py
```

测试内容：
1. VSA信号检测器
2. 市场结构分析器
3. VSA策略
4. 数据库VMA字段
5. 配置文件

## 💡 使用建议

### 1. 策略前提条件
- **只在日线MARK_UP（上涨区）阶段寻找入场机会**
- 这是框架的核心原则，违背此原则的信号会被自动过滤

### 2. 风险管理
- 每个信号都包含建议的止损位和目标位
- 风险回报比至少应在1.5:1以上
- 单只股票仓位不超过20%

### 3. 数据质量
- 确保VMA数据已计算（运行数据更新脚本）
- 至少需要30天历史数据才能准确判断市场结构
- 定期更新数据以保持信号的时效性

### 4. 信号确认
- VSA信号应与其他技术面指标综合判断
- 关注综合评分报告中的`Total_Score`
- 优先选择得分高且VSA信号强的股票

## 📈 实战流程

### 每日操作流程

1. **早盘前（9:00前）**
   ```bash
   # 更新数据
   python database/fetch_data_to_db.py --update
   ```

2. **开盘前（9:15-9:25）**
   ```bash
   # 扫描股票池
   python scripts/vsa_scanner.py --pool my_stocks.txt --output today_signals.csv

   # 查看综合评分
   python scripts/daily_stock_scoring.py --db --stock-pool my_stocks.txt
   ```

3. **盘中（根据信号择机入场）**
   - 参考TEST_ENTRY、BREAKOUT_PULLBACK、SELLING_CLIMAX信号
   - 确保市场结构为MARK_UP
   - 设置止损和目标价

4. **盘后复盘**
   - 分析信号准确性
   - 调整策略参数（如有必要）

## 🔧 故障排除

### 1. "缺少VMA数据"
**问题**：扫描时提示缺少VMA数据

**解决**：
```bash
python database/fetch_data_to_db.py --update
```

### 2. "未发现信号"
**原因**：
- 市场结构不是MARK_UP（上涨区）
- 数据不足（<30天）
- 当前确实无符合条件的信号

**建议**：
- 扩大股票池范围
- 降低参数阈值（修改`config/vsa_config.py`）

### 3. "模块导入失败"
**问题**：`ImportError: No module named 'analysis'`

**解决**：确保在项目根目录运行脚本
```bash
cd /Users/haidongwan/Desktop/stock/ta_stock
python scripts/vsa_scanner.py --pool my_stocks.txt
```

## 📚 参考资料

- 原始设计文档：`duanxian.md`
- 参数配置：`config/vsa_config.py`
- 测试脚本：`test_vsa_framework.py`

## 🎓 学习资源

### VSA理论
- Tom Williams的《Master the Markets》
- Wyckoff方法论

### 量价关系
- 关注"力"（Effort）与"结果"（Result）的关系
- 成交量是价格的先行指标
- 背离（Divergence）揭示市场转折点

---

**祝交易顺利！** 📈

如有问题，请参考测试脚本或查看源代码注释。
