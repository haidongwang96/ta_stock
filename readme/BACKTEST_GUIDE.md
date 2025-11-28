# 股票回测框架使用指南

## 📖 目录

- [简介](#简介)
- [快速开始](#快速开始)
- [框架架构](#框架架构)
- [使用教程](#使用教程)
- [自定义策略](#自定义策略)
- [输出说明](#输出说明)
- [配置参数](#配置参数)
- [常见问题](#常见问题)

---

## 简介

这是一个灵活、可扩展的股票回测框架，专为量化交易策略的回测而设计。

### 主要特性

- ✅ **CSV信号输入**：简单的CSV格式，包含股票代码、日期、仓位比例
- ✅ **完全可编程**：支持自定义策略，继承`StrategyBase`类即可
- ✅ **资金管理**：完整的资金账户模拟，支持手续费、印花税、滑点
- ✅ **详细指标**：计算30+个回测指标（收益率、夏普比率、最大回撤等）
- ✅ **可视化图表**：自动生成净值曲线、回撤曲线、月度收益等图表
- ✅ **本地数据**：直接使用项目本地SQLite数据库，无需联网

---

## 快速开始

### 1. 准备信号文件

创建一个CSV文件（例如`signals.csv`），格式如下：

```csv
ts_code,trade_date,position_ratio
000001.SZ,20240115,0.3
600519.SH,20240120,0.5
000858.SZ,20240125,0.4
```

**字段说明：**
- `ts_code`: 股票代码（格式：XXXXXX.SZ/SH）
- `trade_date`: 买入日期（格式：YYYYMMDD）
- `position_ratio`: 仓位比例（0.0-1.0，表示使用账户资金的百分比）

### 2. 运行回测

```bash
# 基础用法
python scripts/run_backtest.py --signals examples/signals.csv

# 指定初始资金和生成图表
python scripts/run_backtest.py --signals signals.csv --capital 200000 --plot

# 使用止盈止损策略
python scripts/run_backtest.py --signals signals.csv --strategy StopLossStrategy --stop-loss -0.05 --take-profit 0.10

# 保存详细结果
python scripts/run_backtest.py --signals signals.csv --output results/ --plot --save-trades --save-metrics
```

### 3. 查看结果

回测完成后，会在终端输出：
- 回测结果摘要（总收益率、最终资金等）
- 详细回测指标（夏普比率、最大回撤、胜率等）

如果使用`--plot`参数，会在输出目录生成4张图表：
- `equity_curve.png` - 净值曲线
- `drawdown.png` - 回撤曲线
- `monthly_returns.png` - 月度收益热力图
- `trade_distribution.png` - 交易分布图

---

## 框架架构

```
backtesting/
├── backtester.py       # 核心回测引擎
├── portfolio.py        # 资金账户管理
├── position.py         # 持仓管理
├── strategy_base.py    # 策略基类
├── trade_signal.py     # 交易信号
├── metrics.py          # 指标计算
└── visualizer.py       # 可视化

config/
└── backtest_config.py  # 配置参数

scripts/
└── run_backtest.py     # 执行脚本

examples/
├── signals.csv         # 示例信号文件
└── custom_strategy_example.py  # 自定义策略示例
```

---

## 使用教程

### 命令行参数完整列表

```bash
python scripts/run_backtest.py \
  --signals SIGNALS_FILE      # 信号文件路径（必需）
  --capital 100000            # 初始资金
  --commission 0.0003         # 佣金费率
  --stamp-tax 0.001           # 印花税率
  --min-commission 5.0        # 最低佣金
  --slippage 0.0              # 滑点
  --strategy STRATEGY_NAME    # 策略类型
  --hold-days 5               # 持有天数（SimpleHoldStrategy）
  --stop-loss -0.05           # 止损比例（StopLossStrategy）
  --take-profit 0.10          # 止盈比例（StopLossStrategy）
  --max-hold-days 30          # 最大持有天数（StopLossStrategy）
  --preset PRESET_NAME        # 预定义策略配置
  --output OUTPUT_DIR         # 输出目录
  --plot                      # 生成图表
  --save-trades               # 保存交易记录
  --save-metrics              # 保存指标
  --log-level INFO            # 日志级别
```

### 预定义策略配置

框架提供了5个预定义策略配置：

```bash
# 3日持有策略
python scripts/run_backtest.py --signals signals.csv --preset simple_hold_3d

# 5日持有策略（默认）
python scripts/run_backtest.py --signals signals.csv --preset simple_hold_5d

# 10日持有策略
python scripts/run_backtest.py --signals signals.csv --preset simple_hold_10d

# 保守止盈止损（止损3%，止盈6%）
python scripts/run_backtest.py --signals signals.csv --preset stop_loss_conservative

# 激进止盈止损（止损8%，止盈15%）
python scripts/run_backtest.py --signals signals.csv --preset stop_loss_aggressive
```

---

## 自定义策略

### 策略基类接口

所有策略必须继承`StrategyBase`类，并实现以下两个方法：

```python
from backtesting.strategy_base import StrategyBase
import pandas as pd

class MyCustomStrategy(StrategyBase):
    def should_buy(self, ts_code: str, date: str, data: pd.DataFrame,
                   portfolio_value: float, **kwargs) -> bool:
        """
        判断是否应该买入

        Args:
            ts_code: 股票代码
            date: 当前日期
            data: 股票历史数据（包含技术指标）
            portfolio_value: 当前账户总价值

        Returns:
            True表示买入，False表示不买入
        """
        # 在这里实现你的买入逻辑
        return True

    def should_sell(self, ts_code: str, date: str, data: pd.DataFrame,
                    position: any, **kwargs) -> bool:
        """
        判断是否应该卖出

        Args:
            ts_code: 股票代码
            date: 当前日期
            data: 股票历史数据
            position: 当前持仓信息（包含buy_price, current_price, hold_days等）

        Returns:
            True表示卖出，False表示继续持有
        """
        # 在这里实现你的卖出逻辑
        return False
```

### MACD策略示例

```python
class MACDStrategy(StrategyBase):
    """MACD金叉买入，死叉卖出"""

    def should_buy(self, ts_code: str, date: str, data: pd.DataFrame,
                   portfolio_value: float, **kwargs) -> bool:
        # 获取最近两天的MACD数据
        recent_data = data.tail(2)

        # MACD金叉
        if recent_data.iloc[-2]['macd'] <= recent_data.iloc[-2]['macd_signal'] and \
           recent_data.iloc[-1]['macd'] > recent_data.iloc[-1]['macd_signal']:
            return True
        return False

    def should_sell(self, ts_code: str, date: str, data: pd.DataFrame,
                    position: any, **kwargs) -> bool:
        recent_data = data.tail(2)

        # MACD死叉
        if recent_data.iloc[-2]['macd'] >= recent_data.iloc[-2]['macd_signal'] and \
           recent_data.iloc[-1]['macd'] < recent_data.iloc[-1]['macd_signal']:
            return True
        return False
```

### 数据字段说明

`data` DataFrame包含以下字段（来自数据库）：

**OHLCV数据：**
- `trade_date` - 交易日期
- `open` - 开盘价
- `high` - 最高价
- `low` - 最低价
- `close` - 收盘价
- `volume` - 成交量
- `amount` - 成交额

**技术指标：**
- `ma5`, `ma10`, `ma20`, `ma60` - 移动均线
- `macd`, `macd_signal`, `macd_hist` - MACD指标
- `rsi` - RSI指标
- `kdj_k`, `kdj_d`, `kdj_j` - KDJ指标
- `cci` - CCI指标
- `bollinger_upper`, `bollinger_middle`, `bollinger_lower` - 布林带
- `atr` - ATR指标
- `obv` - OBV指标
- `mfi` - MFI指标
- `vwap` - VWAP指标
- `sar` - SAR指标

完整示例请查看 `examples/custom_strategy_example.py`

---

## 输出说明

### 1. 终端输出

**回测结果摘要：**
```
============================================================
回测结果摘要
============================================================
初始资金：100,000.00
最终资金：115,230.00
总收益：15,230.00
总收益率：15.23%
总交易次数：10
总手续费：156.80
已平仓交易：5
策略：SimpleHoldStrategy({'hold_days': 5})
============================================================
```

**详细回测指标：**
```
============================================================
详细回测指标
============================================================

【收益指标】
总收益率：15.23%
年化收益率：28.45%
总盈亏：15,230.00
最终资金：115,230.00

【风险指标】
波动率（年化）：18.56%
最大回撤：-8.32%
最大回撤持续期：15 天
夏普比率：1.37
索提诺比率：1.89
卡玛比率：3.42

【交易统计】
总交易次数：5
盈利次数：4
亏损次数：1
胜率：80.00%
平均盈利：4,820.50
平均亏损：1,250.00
盈亏比：3.86
平均持仓天数：7.2
最大单笔盈利：6,500.00
最大单笔亏损：-1,250.00

【时间统计】
开始日期：20240115
结束日期：20240315
总天数：60
交易日数：42
============================================================
```

### 2. CSV文件输出

**trades.csv** - 详细交易记录
```csv
股票代码,股数,买入日期,买入价格,买入金额,卖出日期,卖出价格,卖出金额,盈亏,收益率,持仓天数,手续费,备注
000001.SZ,2000,20240115,12.50,25030.00,20240120,13.20,26370.00,1340.00,5.35%,5,60.00,
```

**equity_curve.csv** - 净值曲线数据
```csv
date,cash,market_value,total_value,positions_count
20240115,75000.00,25000.00,100000.00,1
20240116,75000.00,25200.00,100200.00,1
...
```

### 3. JSON文件输出

**metrics.json** - 回测指标（机器可读格式）
```json
{
  "total_return": 0.1523,
  "annual_return": 0.2845,
  "volatility": 0.1856,
  "max_drawdown": -0.0832,
  "sharpe_ratio": 1.37,
  ...
}
```

### 4. 图表输出

- **equity_curve.png** - 账户净值曲线，显示资金增长趋势
- **drawdown.png** - 回撤曲线，显示资金回撤情况
- **monthly_returns.png** - 月度收益热力图
- **trade_distribution.png** - 包含4个子图：
  - 盈亏分布直方图
  - 胜率统计饼图
  - 持仓天数分布
  - 累计盈亏曲线

---

## 配置参数

### 在代码中使用配置

```python
from config import backtest_config

# 打印配置
backtest_config.print_config()

# 获取预定义策略
config = backtest_config.get_strategy_config('simple_hold_5d')
```

### 修改默认配置

编辑 `config/backtest_config.py`：

```python
# 修改初始资金
INITIAL_CAPITAL = 200000.0

# 修改佣金费率
COMMISSION_RATE = 0.0002  # 万2

# 修改默认策略
DEFAULT_STRATEGY = 'StopLossStrategy'

# 添加自定义策略配置
STRATEGY_CONFIGS['my_strategy'] = {
    'strategy': 'MyCustomStrategy',
    'params': {'param1': value1, 'param2': value2}
}
```

---

## 常见问题

### Q1: 如何生成信号文件？

你可以使用现有的打分系统或策略扫描器生成信号。例如：

```python
import pandas as pd

# 从打分系统获取高分股票
# 或从VSA扫描器获取信号

signals = []
for stock in selected_stocks:
    signals.append({
        'ts_code': stock['ts_code'],
        'trade_date': stock['date'],
        'position_ratio': 0.3  # 每只股票占30%仓位
    })

# 保存为CSV
df = pd.DataFrame(signals)
df.to_csv('my_signals.csv', index=False)
```

### Q2: 如何对接现有策略（VSA、低位缩量等）？

创建一个策略类继承`StrategyBase`，并在`should_buy`和`should_sell`中调用现有策略的逻辑：

```python
from strategies.vsa_strategy import VSAStrategy as OriginalVSA
from backtesting.strategy_base import StrategyBase

class VSABacktestStrategy(StrategyBase):
    def __init__(self):
        super().__init__()
        self.vsa = OriginalVSA()

    def should_buy(self, ts_code, date, data, portfolio_value, **kwargs):
        # 调用原有VSA策略判断逻辑
        signals = self.vsa.analyze(data)
        return any(s['type'] in ['HEALTHY_UP', 'SUPPLY_DRY_UP'] for s in signals)

    def should_sell(self, ts_code, date, data, position, **kwargs):
        # 实现卖出逻辑
        return position.hold_days >= 10
```

### Q3: 如何批量测试多个策略？

创建一个脚本循环测试：

```python
from backtesting import Backtester
from backtesting.strategy_base import SimpleHoldStrategy

results = {}
for hold_days in [3, 5, 7, 10, 15]:
    strategy = SimpleHoldStrategy(hold_days=hold_days)
    backtester = Backtester('signals.csv', strategy=strategy)
    backtester.run()

    result = backtester.get_results()
    results[f'hold_{hold_days}d'] = result['total_return']

# 比较结果
print(results)
```

### Q4: 回测速度慢怎么办？

- 减少信号数量，先测试小样本
- 使用`--log-level WARNING`减少日志输出
- 确保数据库有正确的索引（已默认创建）

### Q5: 如何复用打分系统作为策略？

```python
from scripts.daily_stock_scoring import StockScoringAnalyzer
from backtesting.strategy_base import StrategyBase

class ScoringStrategy(StrategyBase):
    def should_buy(self, ts_code, date, data, portfolio_value, **kwargs):
        # 计算技术面打分
        analyzer = StockScoringAnalyzer()
        scores = analyzer.calculate_all_scores(data)

        # 总分超过30分才买入
        return scores['total_score'] > 30
```

---

## 联系与反馈

如有问题或建议，请查看项目文档或联系开发者。

**祝回测顺利！** 🚀
