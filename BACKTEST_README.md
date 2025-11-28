# 股票回测框架

一个灵活、可扩展的股票回测框架，支持CSV信号输入、自定义策略、完整的资金管理和详细的回测指标。

## 🚀 快速开始

### 1. 准备信号文件

创建CSV文件 `signals.csv`：

```csv
ts_code,trade_date,position_ratio
000001.SZ,20240115,0.3
600519.SH,20240120,0.5
000858.SZ,20240125,0.4
```

### 2. 运行回测

```bash
# 基础回测
python scripts/run_backtest.py --signals examples/signals.csv

# 生成图表和保存结果
python scripts/run_backtest.py --signals examples/signals.csv --plot --save-trades --save-metrics

# 使用止盈止损策略
python scripts/run_backtest.py --signals examples/signals.csv --strategy StopLossStrategy --stop-loss -0.05 --take-profit 0.10
```

### 3. 查看结果

回测完成后会显示：
- 回测结果摘要（总收益率、最终资金）
- 详细指标（夏普比率、最大回撤、胜率等）
- 图表文件（如果使用了`--plot`）

## 📁 项目结构

```
backtesting/              # 回测核心模块
├── backtester.py        # 回测引擎
├── portfolio.py         # 资金管理
├── position.py          # 持仓管理
├── strategy_base.py     # 策略基类
├── metrics.py           # 指标计算
└── visualizer.py        # 可视化

config/
└── backtest_config.py   # 配置参数

scripts/
└── run_backtest.py      # 执行脚本

examples/
├── signals.csv          # 示例信号
└── custom_strategy_example.py  # 自定义策略示例

readme/
└── BACKTEST_GUIDE.md    # 详细使用指南
```

## ✨ 核心特性

### 1. CSV信号输入
简单的CSV格式，包含股票代码、日期、仓位比例

### 2. 完全可编程
继承`StrategyBase`类即可实现自定义策略：

```python
from backtesting.strategy_base import StrategyBase

class MyStrategy(StrategyBase):
    def should_buy(self, ts_code, date, data, portfolio_value, **kwargs):
        # 实现买入逻辑
        return True

    def should_sell(self, ts_code, date, data, position, **kwargs):
        # 实现卖出逻辑
        return position.hold_days >= 5
```

### 3. 资金管理
- 手续费：万3佣金（可配置）
- 印花税：千1（卖出时）
- 滑点：可配置
- 最低佣金：5元

### 4. 详细指标
计算30+个回测指标：
- **收益指标**：总收益率、年化收益率
- **风险指标**：夏普比率、最大回撤、波动率
- **交易统计**：胜率、盈亏比、平均持仓天数

### 5. 可视化图表
自动生成4张专业图表：
- 净值曲线
- 回撤曲线
- 月度收益热力图
- 交易分布图

### 6. 本地数据
直接使用项目SQLite数据库，无需联网

## 📊 内置策略

### SimpleHoldStrategy（简单持有）
在信号日买入，持有N天后卖出

```bash
python scripts/run_backtest.py --signals signals.csv --strategy SimpleHoldStrategy --hold-days 5
```

### StopLossStrategy（止盈止损）
支持止盈、止损和最大持有天数

```bash
python scripts/run_backtest.py --signals signals.csv --strategy StopLossStrategy --stop-loss -0.05 --take-profit 0.10
```

### 预定义配置
使用`--preset`参数快速选择：

```bash
# 3日持有
python scripts/run_backtest.py --signals signals.csv --preset simple_hold_3d

# 保守止盈止损
python scripts/run_backtest.py --signals signals.csv --preset stop_loss_conservative

# 激进止盈止损
python scripts/run_backtest.py --signals signals.csv --preset stop_loss_aggressive
```

## 🎯 使用场景

### 1. 测试交易信号
将你的选股逻辑生成的信号文件进行回测，验证有效性

### 2. 策略对比
测试不同持有天数、止盈止损参数的效果

### 3. 风险评估
通过最大回撤、夏普比率等指标评估策略风险

### 4. 与现有策略集成
可以对接项目中已有的VSA策略、低位缩量策略等

## 📖 详细文档

查看完整使用指南：[readme/BACKTEST_GUIDE.md](readme/BACKTEST_GUIDE.md)

内容包括：
- 详细的命令行参数说明
- 自定义策略开发教程
- 输出文件格式说明
- 常见问题解答
- 与现有代码集成方法

## 🔧 配置参数

主要配置在 `config/backtest_config.py`：

```python
# 资金管理
INITIAL_CAPITAL = 100000.0      # 初始资金
COMMISSION_RATE = 0.0003        # 佣金费率
STAMP_TAX_RATE = 0.001          # 印花税率
MIN_COMMISSION = 5.0            # 最低佣金
SLIPPAGE = 0.0                  # 滑点

# 输出
OUTPUT_DIR = './backtest_results'
GENERATE_PLOTS = True
SAVE_TRADES = True
```

## 📝 示例

### 示例1：基础回测

```bash
python scripts/run_backtest.py \
  --signals examples/signals.csv \
  --capital 100000 \
  --plot
```

### 示例2：使用自定义策略

```python
# 在 examples/custom_strategy_example.py 中查看MACD和RSI策略示例
from backtesting import Backtester
from examples.custom_strategy_example import MACDStrategy

strategy = MACDStrategy(max_hold_days=20)
backtester = Backtester('signals.csv', strategy=strategy)
backtester.run()
```

### 示例3：批量测试参数

```python
results = {}
for hold_days in [3, 5, 7, 10]:
    backtester = Backtester(
        'signals.csv',
        strategy=SimpleHoldStrategy(hold_days=hold_days)
    )
    backtester.run()
    results[hold_days] = backtester.get_results()['total_return']
```

## 🎓 进阶用法

### 对接现有打分系统

```python
from scripts.daily_stock_scoring import StockScoringAnalyzer
from backtesting.strategy_base import StrategyBase

class ScoringStrategy(StrategyBase):
    def should_buy(self, ts_code, date, data, portfolio_value, **kwargs):
        analyzer = StockScoringAnalyzer()
        scores = analyzer.calculate_all_scores(data)
        return scores['total_score'] > 30  # 总分>30才买入
```

### 结合VSA策略

```python
from strategies.vsa_strategy import VSAStrategy
from backtesting.strategy_base import StrategyBase

class VSABacktestStrategy(StrategyBase):
    def __init__(self):
        super().__init__()
        self.vsa = VSAStrategy()

    def should_buy(self, ts_code, date, data, portfolio_value, **kwargs):
        signals = self.vsa.analyze(data)
        return any(s['type'] == 'SUPPLY_DRY_UP' for s in signals)
```

## 🚧 注意事项

1. **数据完整性**：确保信号中的股票在数据库中有对应的历史数据
2. **日期格式**：信号文件中的日期必须是YYYYMMDD格式
3. **仓位比例**：position_ratio范围为0.0-1.0
4. **停牌处理**：回测引擎会自动跳过无交易数据的日期

## 📞 帮助

运行帮助命令查看所有参数：

```bash
python scripts/run_backtest.py --help
```

---

**开始你的回测之旅吧！** 🎉
